翻译模型 / 服务说明
====================

本工具支持两种开源翻译方式：

1) 本地 LibreTranslate（推荐离线/绿色内网）
   - 安装开源项目：https://github.com/LibreTranslate/LibreTranslate
   - 启动后在本目录 config.json 填写：
       "libreTranslateUrl": "http://127.0.0.1:5000"
   - LibreTranslate 使用 Argos Translate 开源模型，模型可本地缓存

2) 默认开源客户端 GTranslate
   - 无需额外部署，联网即可中英互译
   - 适合便携分发的开箱体验

对照显示：原文行（绿色）+ 译文行（白色）交替排列。
