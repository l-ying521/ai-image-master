# PixMagic - 图像增强工具

基于百度 AI 开放平台的在线图像处理工具，提供多种图像增强功能。

## ✨ 功能特性

- 🖼️ 图像无损放大
- 🌫️ 图像去雾
- 🎨 图像对比度增强
- 🔧 拉伸图像恢复
- 🛠️ 图像修复（暂使用对比度增强）
- 👁️ 图像清晰度增强
- 🎭 图像色彩增强
- 📱 图片去摩尔纹
- 📄 文档图片去底纹
- ✂️ 智能抠图

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
2. 配置 API 密钥
在 baidu_api.py 中直接填写你的百度 AI API Key 和 Secret Key（位于 Config 类中）。比赛提交时请务必替换为占位符，避免泄露。

3. 运行服务
bash
python app.py
服务将在 http://localhost:5000 启动。

📋 使用说明
打开浏览器访问 http://localhost:5000

在左侧工具栏选择需要使用的图像增强功能

拖拽或点击上传图片（支持 JPG、PNG、WEBP，单张不超过 10MB）

点击“开始增强”，等待处理完成，自动跳转结果页

在结果页可切换查看原图、增强后图片及差异对比，并支持导出处理结果

⚙️ 配置说明
图片大小限制：在 baidu_api.py 中修改 Config.MAX_IMAGE_SIZE（默认 10MB）

API 重试策略：可在 baidu_api.py 中调整 MAX_RETRIES、RETRY_DELAY

🛠️ 技术栈
后端: Flask 3.0

图像处理: Pillow

HTTP 请求: Requests

AI 服务: 百度 AI 开放平台

⚠️ 注意事项
API 配额: 百度 AI 免费额度有限，请留意控制台剩余次数

文件大小: 单张图片不超过 10MB

格式支持: JPG, PNG, WEBP

网络要求: 需要稳定的网络连接百度 AI 服务

📄 License
MIT License

👤 作者
Created with ❤️ by PixMagic Team

