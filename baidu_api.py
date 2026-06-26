import requests
import base64
import logging
import time
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# ========== 日志配置 ==========
logger = logging.getLogger(__name__)

# ========== 配置管理 ==========
class Config:
    # API 密钥（从环境变量读取，必须配置）
    API_KEY = os.getenv('BAIDU_API_KEY')
    SECRET_KEY = os.getenv('BAIDU_SECRET_KEY')

    # 验证 API 密钥是否配置
    if not API_KEY or not SECRET_KEY:
        logger.warning("百度 API 密钥未配置，请在 .env 文件中设置 BAIDU_API_KEY 和 BAIDU_SECRET_KEY")

    # 请求配置
    TIMEOUT = 30
    MAX_RETRIES = 3
    RETRY_DELAY = 1
    MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB

# ========== 全局变量 ==========
_access_token_cache = {
    'token': None,
    'expire_time': None
}

# ========== 辅助函数 ==========
def get_access_token(force_refresh=False):
    """获取百度 AI 的 access_token（带缓存）"""
    global _access_token_cache

    # 验证 API 密钥是否配置
    if not Config.API_KEY or not Config.SECRET_KEY:
        raise Exception("百度 API 密钥未配置，请在 .env 文件中设置 BAIDU_API_KEY 和 BAIDU_SECRET_KEY")

    if not force_refresh and _access_token_cache['token']:
        if datetime.now() < _access_token_cache['expire_time']:
            logger.debug("使用缓存的 access_token")
            return _access_token_cache['token']

    try:
        logger.info("正在获取新的 access_token...")
        url = "https://aip.baidubce.com/oauth/2.0/token"
        params = {
            "grant_type": "client_credentials",
            "client_id": Config.API_KEY,
            "client_secret": Config.SECRET_KEY
        }
        response = requests.post(url, params=params, timeout=Config.TIMEOUT)
        response.raise_for_status()
        result = response.json()
        access_token = result.get("access_token")
        if not access_token:
            logger.error(f"获取 access_token 失败：{result}")
            raise Exception(f"百度 API 认证失败：{result.get('error_description', 'Unknown error')}")

        expires_in = result.get('expires_in', 2592000)
        _access_token_cache['token'] = access_token
        _access_token_cache['expire_time'] = datetime.now() + timedelta(seconds=expires_in - 86400)
        logger.info("access_token 获取成功")
        return access_token
    except requests.exceptions.Timeout:
        logger.error("获取 access_token 超时")
        raise Exception("百度 API 连接超时，请检查网络连接")
    except requests.exceptions.ConnectionError as e:
        logger.error(f"获取 access_token 连接失败：{e}")
        raise Exception("无法连接到百度 API，请检查网络连接")
    except Exception as e:
        logger.error(f"获取 access_token 异常：{e}", exc_info=True)
        raise

def build_api_url(endpoint, access_token):
    return f"https://aip.baidubce.com{endpoint}?access_token={access_token}"

def call_baidu_api(url, payload, headers=None):
    """调用百度 API（带重试机制）"""
    if headers is None:
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    last_exception = None
    
    for attempt in range(Config.MAX_RETRIES):
        try:
            response = requests.post(url, data=payload, headers=headers, timeout=Config.TIMEOUT)
            response.raise_for_status()
            result = response.json()
            if 'error_code' in result:
                error_msg = f"API 错误：{result.get('error_msg', 'Unknown error')} (代码：{result.get('error_code')})"
                logger.error(error_msg)
                if result.get('error_code') in ['110', '111']:
                    logger.warning("Token 可能已过期，尝试刷新...")
                    get_access_token(force_refresh=True)
                    url_parts = url.split('?access_token=')
                    if len(url_parts) == 2:
                        url = f"{url_parts[0]}?access_token={get_access_token()}"
                        continue
                return {'error': error_msg, 'raw': result}
            return result
        except requests.exceptions.Timeout:
            last_exception = Exception(f"请求超时（{Config.TIMEOUT}秒）")
            logger.warning(f"请求超时，将在 {Config.RETRY_DELAY}秒后重试...")
        except requests.exceptions.ConnectionError as e:
            last_exception = Exception(f"网络连接错误：{str(e)}")
            logger.warning(f"网络连接失败，将在 {Config.RETRY_DELAY}秒后重试...")
        except requests.exceptions.RequestException as e:
            last_exception = Exception(f"HTTP 请求错误：{str(e)}")
            logger.error(f"HTTP 请求错误：{e}")
            return {'error': str(last_exception)}
        except Exception as e:
            last_exception = e
            logger.error(f"未知错误：{e}")
            return {'error': f"处理异常：{str(e)}"}
        if attempt < Config.MAX_RETRIES - 1:
            time.sleep(Config.RETRY_DELAY)
    
    error_msg = f"API 调用失败（已重试{Config.MAX_RETRIES}次）: {str(last_exception)}"
    logger.error(error_msg)
    return {'error': error_msg}

# ========== 图片大小校验 ==========
def _validate_image_size(image_bytes):
    if len(image_bytes) > Config.MAX_IMAGE_SIZE:
        return {'error': f'图片大小超过 {Config.MAX_IMAGE_SIZE // (1024*1024)}MB 限制，请缩小后重试'}
    return None

# ========== 图像增强系列 ==========
def enhance_image(image_bytes):
    error = _validate_image_size(image_bytes)
    if error: return error
    try:
        access_token = get_access_token()
        url = build_api_url("/rest/2.0/image-process/v1/contrast_enhance", access_token)
        img_base64 = base64.b64encode(image_bytes).decode('utf-8')
        payload = {"image": img_base64, "image_type": "BASE64"}
        result = call_baidu_api(url, payload)
        if 'error' in result:
            return result
        if 'image' in result:
            logger.info("图像对比度增强成功")
            return {'image': result['image']}
        else:
            return {'error': 'API 返回数据格式异常'}
    except Exception as e:
        logger.error(f"图像对比度增强失败：{e}", exc_info=True)
        return {'error': f"处理异常：{str(e)}"}

def dehaze_image(image_bytes):
    error = _validate_image_size(image_bytes)
    if error: return error
    try:
        access_token = get_access_token()
        url = build_api_url("/rest/2.0/image-process/v1/dehaze", access_token)
        img_base64 = base64.b64encode(image_bytes).decode('utf-8')
        payload = {"image": img_base64, "image_type": "BASE64"}
        result = call_baidu_api(url, payload)
        if 'error' in result:
            return result
        if 'image' in result:
            logger.info("图像去雾成功")
            return {'image': result['image']}
        else:
            return {'error': 'API 返回数据格式异常'}
    except Exception as e:
        logger.error(f"图像去雾失败：{e}", exc_info=True)
        return {'error': f"处理异常：{str(e)}"}

def enhance_definition(image_bytes):
    error = _validate_image_size(image_bytes)
    if error: return error
    try:
        access_token = get_access_token()
        url = build_api_url("/rest/2.0/image-process/v1/image_definition_enhance", access_token)
        img_base64 = base64.b64encode(image_bytes).decode('utf-8')
        payload = {"image": img_base64, "image_type": "BASE64"}
        result = call_baidu_api(url, payload)
        if 'error' in result:
            return result
        if 'image' in result:
            logger.info("图像清晰度增强成功")
            return {'image': result['image']}
        else:
            return {'error': 'API 返回数据格式异常'}
    except Exception as e:
        logger.error(f"图像清晰度增强失败：{e}", exc_info=True)
        return {'error': f"处理异常：{str(e)}"}

def color_enhance(image_bytes):
    error = _validate_image_size(image_bytes)
    if error: return error
    try:
        access_token = get_access_token()
        url = build_api_url("/rest/2.0/image-process/v1/color_enhance", access_token)
        img_base64 = base64.b64encode(image_bytes).decode('utf-8')
        payload = {"image": img_base64, "image_type": "BASE64"}
        result = call_baidu_api(url, payload)
        if 'error' in result:
            return result
        if 'image' in result:
            logger.info("图像色彩增强成功")
            return {'image': result['image']}
        else:
            return {'error': 'API 返回数据格式异常'}
    except Exception as e:
        logger.error(f"图像色彩增强失败：{e}", exc_info=True)
        return {'error': f"处理异常：{str(e)}"}

def stretch_restore(image_bytes):
    error = _validate_image_size(image_bytes)
    if error: return error
    try:
        access_token = get_access_token()
        url = build_api_url("/rest/2.0/image-process/v1/stretch_restore", access_token)
        img_base64 = base64.b64encode(image_bytes).decode('utf-8')
        payload = {"image": img_base64, "image_type": "BASE64"}
        result = call_baidu_api(url, payload)
        if 'error' in result:
            return result
        if 'image' in result:
            logger.info("拉伸图像恢复成功")
            return {'image': result['image']}
        else:
            return {'error': 'API 返回数据格式异常'}
    except Exception as e:
        logger.error(f"拉伸图像恢复失败：{e}", exc_info=True)
        return {'error': f"处理异常：{str(e)}"}

def quality_enhance(image_bytes):
    error = _validate_image_size(image_bytes)
    if error: return error
    try:
        access_token = get_access_token()
        url = build_api_url("/rest/2.0/image-process/v1/image_quality_enhance", access_token)
        img_base64 = base64.b64encode(image_bytes).decode('utf-8')
        payload = {"image": img_base64, "image_type": "BASE64"}
        result = call_baidu_api(url, payload)
        if 'error' in result:
            return result
        if 'image' in result:
            logger.info("图像无损放大成功")
            return {'image': result['image']}
        else:
            return {'error': 'API 返回数据格式异常'}
    except Exception as e:
        logger.error(f"图像无损放大失败：{e}", exc_info=True)
        return {'error': f"处理异常：{str(e)}"}

def moire_removal(image_bytes):
    error = _validate_image_size(image_bytes)
    if error: return error
    try:
        access_token = get_access_token()
        url = build_api_url("/rest/2.0/image-process/v1/moire_removal", access_token)
        img_base64 = base64.b64encode(image_bytes).decode('utf-8')
        payload = {"image": img_base64, "image_type": "BASE64"}
        result = call_baidu_api(url, payload)
        if 'error' in result:
            return result
        if 'image' in result:
            logger.info("图片去摩尔纹成功")
            return {'image': result['image']}
        else:
            return {'error': 'API 返回数据格式异常'}
    except Exception as e:
        logger.error(f"图片去摩尔纹失败：{e}", exc_info=True)
        return {'error': f"处理异常：{str(e)}"}

def document_removal(image_bytes):
    error = _validate_image_size(image_bytes)
    if error: return error
    try:
        access_token = get_access_token()
        url = build_api_url("/rest/2.0/image-process/v1/document_removal", access_token)
        img_base64 = base64.b64encode(image_bytes).decode('utf-8')
        payload = {"image": img_base64, "image_type": "BASE64"}
        result = call_baidu_api(url, payload)
        if 'error' in result:
            return result
        if 'image' in result:
            logger.info("文档图片去底纹成功")
            return {'image': result['image']}
        else:
            return {'error': 'API 返回数据格式异常'}
    except Exception as e:
        logger.error(f"文档图片去底纹失败：{e}", exc_info=True)
        return {'error': f"处理异常：{str(e)}"}

def matting_image(image_bytes):
    error = _validate_image_size(image_bytes)
    if error: return error
    try:
        access_token = get_access_token()
        # 使用百度人像抠图 API（效果更佳）
        url = build_api_url("/rest/2.0/image-process/v1/selfie_matting", access_token)
        img_base64 = base64.b64encode(image_bytes).decode('utf-8')
        payload = {"image": img_base64}
        result = call_baidu_api(url, payload)
        if 'error' in result:
            logger.error(f"抠图 API 返回错误：{result['error']}")
            return result
        if 'image' in result and result['image']:
            logger.info("智能抠图成功，返回带透明通道的人像图片")
            return {'image': result['image']}
        else:
            logger.warning("抠图失败：未检测到人物或 API 返回数据异常")
            return {'error': '未检测到人物或抠图失败，请确保图片中包含清晰的人物'}
    except Exception as e:
        logger.error(f"智能抠图失败：{e}", exc_info=True)
        return {'error': f"处理异常：{str(e)}"}

# ========== 工具函数 ==========
def test_api_connection():
    try:
        token = get_access_token()
        return bool(token)
    except Exception as e:
        logger.error(f"API 连接测试失败：{e}")
        return False

def get_api_usage_stats():
    return {
        'token_cached': _access_token_cache['token'] is not None,
        'token_expire_time': _access_token_cache['expire_time'].isoformat() if _access_token_cache['expire_time'] else None,
        'config': {
            'timeout': Config.TIMEOUT,
            'max_retries': Config.MAX_RETRIES,
            'retry_delay': Config.RETRY_DELAY,
            'max_image_size_mb': Config.MAX_IMAGE_SIZE // (1024*1024)
        }
    }
