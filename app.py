from flask import Flask, render_template, request, jsonify, session, redirect, url_for, make_response
import base64
import logging
import os
from PIL import Image
from io import BytesIO
from functools import wraps
from datetime import datetime
import uuid
from dotenv import load_dotenv
from baidu_api import (
    enhance_image,
    dehaze_image,
    enhance_definition,
    color_enhance,
    stretch_restore,
    quality_enhance,
    moire_removal,
    document_removal,
    matting_image
)

# 加载环境变量
load_dotenv()

# ========== 配置管理 ==========
class Config:
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB 总限制
    ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}
    MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 单张图片 10MB
    API_TIMEOUT = 60
    DEBUG = True
    UPLOAD_DIR = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
    PROCESSED_DIR = os.path.join(os.path.dirname(__file__), 'static', 'processed')

# ========== 应用初始化 ==========
app = Flask(__name__)
app.config.from_object(Config)
# 使用固定的 secret key（生产环境应使用环境变量）
app.secret_key = os.getenv('SECRET_KEY', os.urandom(24).hex())
# Session 配置
app.config['SESSION_COOKIE_NAME'] = 'pixmagic_session'
app.config['SESSION_COOKIE_MAX_AGE'] = 3600  # 1小时
app.config['SESSION_COOKIE_SECURE'] = False  # 开发环境设为 False
app.config['SESSION_COOKIE_HTTPONLY'] = True

os.makedirs(Config.UPLOAD_DIR, exist_ok=True)
os.makedirs(Config.PROCESSED_DIR, exist_ok=True)

# ========== 日志配置 ==========
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
logger = logging.getLogger(__name__)

# ========== 功能映射 ==========
FUNCTION_MAP = {
    'quality_enhance': ('图像无损放大', quality_enhance),
    'dehaze': ('图像去雾', dehaze_image),
    'contrast_enhance': ('图像对比度增强', enhance_image),
    'stretch_restore': ('拉伸图像恢复', stretch_restore),
    'image_restore': ('图像修复', enhance_image),  # 暂用对比度增强
    'definition_enhance': ('图像清晰度增强', enhance_definition),
    'color_enhance': ('图像色彩增强', color_enhance),
    'moire_removal': ('图片去摩尔纹', moire_removal),
    'document_removal': ('文档图片去底纹', document_removal),
    'matting': ('智能抠图', matting_image)
}

# ========== 辅助函数 ==========
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def validate_file(file):
    if not file or not file.filename:
        return False, "没有选择文件"
    if file.filename == '':
        return False, "文件名不能为空"
    if not allowed_file(file.filename):
        return False, f"不支持的文件格式，仅支持：{', '.join(app.config['ALLOWED_EXTENSIONS'])}"
    try:
        file_bytes = file.read()
        if len(file_bytes) > app.config['MAX_IMAGE_SIZE']:
            return False, f"文件大小超过限制（最大 10MB）"
        try:
            Image.open(BytesIO(file_bytes))
        except Exception:
            return False, "文件损坏或不是有效的图片"
        file.seek(0)
        return True, file_bytes
    except Exception as e:
        logger.error(f"文件验证失败：{e}")
        return False, "文件读取失败"

def format_file_size(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"

def get_image_dimensions(file_bytes):
    try:
        img = Image.open(BytesIO(file_bytes))
        width, height = img.size
        return f"{width}x{height}"
    except Exception:
        return "未知尺寸"

def save_image_to_file(file_bytes, save_dir, prefix):
    """保存图片到文件，返回访问路径"""
    file_ext = 'png'
    unique_filename = f"{prefix}_{uuid.uuid4().hex}.{file_ext}"
    save_path = os.path.join(save_dir, unique_filename)
    try:
        img = Image.open(BytesIO(file_bytes))
        # 如果图片有透明通道，保持 RGBA 模式；否则转换为 RGB
        if img.mode in ('RGBA', 'LA', 'P'):
            img.save(save_path, format='PNG')
        else:
            # 对于 JPEG 等格式，转换为 RGB 后保存为 PNG
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img.save(save_path, format='PNG')
        dir_name = os.path.basename(save_dir)
        logger.info(f"图片保存成功：{unique_filename}")
        return f"/static/{dir_name}/{unique_filename}"
    except Exception as e:
        logger.error(f"保存图片失败：{e}", exc_info=True)
        raise Exception(f"保存图片失败：{str(e)}")

def error_handler(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            logger.error(f"请求处理异常：{e}", exc_info=True)
            if request.is_json:
                return jsonify({'error': str(e)}), 500
            return render_template('error.html', error=str(e)), 500
    return wrapper

# ========== 路由 ==========
@app.route('/')
def home():
    response = make_response(render_template('index.html'))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '2.0'
    })

@app.route('/result')
def result():
    task_id = request.args.get('task_id')
    if not task_id:
        return render_template('error.html', error="缺少任务 ID"), 400
    # 使用 pop 删除 session 数据，避免累积
    result_data = session.pop(f'result_{task_id}', None)
    if not result_data:
        return render_template('error.html', error="结果已过期或不存在，请重新处理"), 404
    return render_template('result.html', **result_data)

@app.route('/enhance', methods=['POST'])
@error_handler
def enhance():
    start_time = datetime.now()
    if 'image' not in request.files:
        if request.is_json:
            return jsonify({'error': '没有上传文件'}), 400
        return render_template('error.html', error="没有上传文件"), 400

    files = request.files.getlist('image')
    function_type = request.form.get('function', 'contrast_enhance')
    if function_type not in FUNCTION_MAP:
        function_type = 'contrast_enhance'
    function_name, process_func = FUNCTION_MAP[function_type]
    logger.info(f"收到处理请求：{function_name}, 文件数量：{len(files)}")

    results = []
    for file in files:
        is_valid, result = validate_file(file)
        if not is_valid:
            logger.error(f"文件验证失败：{file.filename} - {result}")
            if request.is_json:
                results.append({'filename': file.filename, 'success': False, 'error': result})
                continue
            return render_template('error.html', error=f"文件验证失败：{result}"), 400

        file_bytes = result
        original_filename = file.filename          # 保存原始文件名
        file_size = len(file_bytes)
        dimensions = get_image_dimensions(file_bytes)
        size_str = format_file_size(file_size)

        try:
            process_result = process_func(file_bytes)
            if 'image' in process_result:
                enhanced_bytes = base64.b64decode(process_result['image'])
                original_path = save_image_to_file(file_bytes, Config.UPLOAD_DIR, 'original')
                enhanced_path = save_image_to_file(enhanced_bytes, Config.PROCESSED_DIR, 'enhanced')
                processing_time = (datetime.now() - start_time).total_seconds()
                logger.info(f"图片处理成功：{original_filename}, 耗时：{processing_time:.2f}s")
                result_data = {
                    'original_path': original_path,
                    'enhanced_path': enhanced_path,
                    'filename': original_filename,      # 使用原始文件名
                    'filesize': size_str,
                    'dimensions': dimensions,
                    'function': function_name,
                    'processing_time': f"{processing_time:.2f}s"
                }
                results.append(result_data)
            else:
                error_msg = f"处理失败：{process_result}"
                logger.error(error_msg)
                if request.is_json:
                    results.append({'filename': original_filename, 'success': False, 'error': error_msg})
                else:
                    return render_template('error.html', error=error_msg), 500
        except Exception as e:
            error_msg = f"处理异常：{str(e)}"
            logger.error(error_msg, exc_info=True)
            if request.is_json:
                results.append({'filename': original_filename, 'success': False, 'error': error_msg})
            else:
                return render_template('error.html', error=error_msg), 500

    if len(results) == 1 and 'original_path' in results[0]:
        result_data = results[0]
        task_id = str(uuid.uuid4())
        session[f'result_{task_id}'] = result_data
        return redirect(url_for('result', task_id=task_id))
    elif len(results) > 1:
        return jsonify({
            'total': len(results),
            'success_count': sum(1 for r in results if r.get('success', True)),
            'results': results
        })
    else:
        return jsonify({'success': False, 'error': '处理失败，请检查日志'}), 500

@app.route('/api/functions', methods=['GET'])
def list_functions():
    functions = [{'key': key, 'name': value[0], 'available': True} for key, value in FUNCTION_MAP.items()]
    return jsonify({'functions': functions})

# ========== 错误页面 ==========
@app.errorhandler(404)
def not_found(error):
    return render_template('error.html', error="页面未找到"), 404

@app.errorhandler(413)
def too_large(error):
    return render_template('error.html', error="文件过大，超过 50MB 限制"), 413

@app.errorhandler(500)
def internal_error(error):
    return render_template('error.html', error="服务器内部错误"), 500

# ========== 启动 ==========
if __name__ == '__main__':
    logger.info("启动 PixMagic 图像增强服务...")
    logger.info(f"支持的图片格式：{', '.join(app.config['ALLOWED_EXTENSIONS'])}")
    logger.info(f"最大文件大小：{format_file_size(app.config['MAX_IMAGE_SIZE'])}")
    host = os.getenv('FLASK_HOST', '127.0.0.1')
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'
    app.run(debug=debug, host=host, port=port, threaded=True)