# CLAUDE.md

本文件为在此仓库中工作的 Claude Code (claude.ai/code) 提供指导。

## 开发命令

### 构建和运行
```bash
# 构建 Angular UI
cd ui
npm install
node_modules/.bin/ng build

# 安装 Python 依赖
cd ..
pip3 install pipenv
pipenv install

# 本地运行应用
pipenv run python3 app/main.py
```

### 前端开发
```bash
cd ui
npm run start     # 开发服务器
npm run build     # 生产构建
npm run lint      # TypeScript 代码检查
```

### Python 开发
```bash
pipenv install --dev    # 安装开发依赖（包含 pylint）
pipenv run pylint app/   # Python 代码检查
```

### Docker
```bash
# 构建 Docker 镜像
docker build -t metube .

# 使用 Docker 运行
docker run -d -p 8081:8081 -v /path/to/downloads:/downloads metube
```

## 项目架构

MeTube 是 yt-dlp 的 Web GUI，具有以下架构：

### 后端 (Python)
- **框架**: aiohttp + Socket.IO 实现实时通信
- **主入口**: `app/main.py` - Web 服务器、API 路由和 Socket.IO 处理器
- **下载引擎**: `app/ytdl.py` - 管理下载队列、yt-dlp 集成和后台任务
- **格式处理**: `app/dl_formats.py` - 视频/音频格式定义和选项

### 前端 (Angular)
- **位置**: `ui/` 目录
- **主组件**: `ui/src/app/app.component.ts`
- **服务**:
  - `downloads.service.ts` - 管理下载操作
  - `metube-socket.ts` - Socket.IO 客户端封装
  - `speed.service.ts` - 下载速度计算
- **构建输出**: `ui/dist/metube/browser/` (由 Python 后端提供)

### 关键集成点
- Socket.IO 在前后端之间的实时更新
- REST API 端点 (`/add`, `/delete`, `/start`, `/history`)
- 下载文件和 UI 资源的静态文件服务
- 通过 `Config` 类加载的环境变量配置

### 下载流程
1. 前端向 `/add` 端点发送下载请求
2. 后端创建 `DownloadInfo` 对象并加入队列
3. `DownloadQueue` 使用 yt-dlp 管理并发下载
4. 通过 Socket.IO 发送实时进度更新
5. 完成的下载存储在持久化队列状态中

### 状态管理
- 使用 Python `shelve` 模块在 `STATE_DIR` 中持久化下载
- 三种下载状态：queue (活动)、done (完成)、pending (未开始)
- 配置从环境变量加载，支持文件监控

## MCP 服务配置

### 文件系统 MCP 服务
```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/kemengkai/Documents/代码项目/python/metube"],
      "env": {}
    }
  }
}
```

### GitHub MCP 服务
```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "your_github_token_here"
      }
    }
  }
}
```

### Browser MCP 服务（用于 Web 自动化测试）
```json
{
  "mcpServers": {
    "browser": {
      "command": "npx",
      "args": ["@browsermcp/mcp@latest"],
      "env": {}
    }
  }
}
```

## Agents 配置

### 代码审查 Agent
- **用途**: 自动代码审查和质量检查
- **触发条件**: 完成重要代码编写后
- **关注点**: Python 代码规范、TypeScript 最佳实践、安全性检查

### 测试 Agent
- **用途**: 通过浏览器进行用户行为测试和功能验证
- **触发条件**: 代码变更后或功能实现完成后
- **测试方式**: 使用 Browser MCP 工具模拟真实用户操作
- **覆盖范围**:
  - Web UI 功能测试
  - 下载流程验证
  - 实时状态更新测试
  - 跨浏览器兼容性验证

### 部署 Agent
- **用途**: 自动化 Docker 构建和部署流程
- **触发条件**: 代码合并到主分支
- **功能**: 镜像构建、依赖检查、部署验证

### 依赖管理 Agent
- **用途**: 监控和更新项目依赖
- **关注点**:
  - Python: Pipfile 中的包更新
  - Node.js: package.json 中的包更新
  - 安全漏洞检测

## 开发最佳实践

### Git 工作流程
- **分支管理**: 每次有修改或新需求时，必须创建新的功能分支
- **提交规范**: 对所有操作、修改和总结都要进行详细的 Git 提交
- **审核流程**: 分支完成后创建 Pull Request，方便审核者查看所有变更
- **分支命名**: 使用描述性名称，如 `feature/download-queue-optimization` 或 `fix/socket-connection-issue`
- **提交信息**: 使用清晰的中文提交信息，说明修改内容和原因

### 环境变量管理
- 本地开发使用 `.env` 文件
- Docker 部署使用环境变量注入
- 敏感配置（如 API 密钥）不要提交到代码库

### 实时通信调试
- 使用浏览器开发者工具监控 Socket.IO 消息
- 后端日志级别设置为 `DEBUG` 查看详细信息
- 测试并发下载时注意内存和 CPU 使用

### 前后端联调
- 前端开发服务器默认代理到 `localhost:8081`
- 后端 CORS 配置允许开发环境跨域请求
- Socket.IO 连接确保在两端都正确配置

## 测试指南

### 重要原则
**所有测试必须通过浏览器进行真实用户操作，禁止使用命令行、Python、bash等脚本进行代码测试。**

### 测试环境准备
1. 启动本地开发服务器：`pipenv run python3 app/main.py`
2. 使用 Browser MCP 工具打开 `http://localhost:8081`
3. 确保网络连接正常，可访问视频网站或音频网站

### 基础功能测试

#### 1. 界面加载测试
- 访问 `http://localhost:8081`
- 验证页面完整加载，所有元素显示正常
- 检查主题切换功能（light/dark/auto）
- 验证响应式设计在不同屏幕尺寸下的表现

#### 2. 下载功能测试
- **单个视频下载**：
  1. 在 URL 输入框中输入需要测试的视频链接或音频连接
  2. 选择质量选项（Best, 720p, 480p等）
  3. 选择格式（MP4, WEBM, MP3等）
  4. 点击"Add"按钮
  5. 观察下载任务是否正确添加到队列
  6. 监控下载进度实时更新
  7. 验证下载完成后状态变化

- **播放列表下载**：
  1. 输入需要测试的视频或音频播放列表链接
  2. 测试"Strict Playlist mode"开关
  3. 设置播放列表项目限制
  4. 验证批量下载功能

- **音频下载测试**：
  1. 选择音频格式（MP3, M4A等）
  2. 测试音频质量选项
  3. 验证音频文件下载

#### 3. 实时更新测试
- 观察下载进度条实时更新
- 检查下载速度显示
- 验证 ETA（预计完成时间）计算
- 测试多个并发下载的状态更新

#### 4. 队列管理测试
- **队列操作**：
  1. 添加多个下载任务
  2. 测试暂停/恢复功能
  3. 测试删除功能
  4. 测试清空队列功能

- **状态切换**：
  1. 验证任务状态：pending → downloading → completed
  2. 测试错误状态处理
  3. 测试重试机制

#### 5. 文件管理测试
- 测试自定义下载目录功能
- 验证文件名模板设置
- 测试下载文件的访问和播放

### 高级功能测试

#### 1. 配置选项测试
- 测试各种 YTDL_OPTIONS 设置
- 验证输出模板自定义
- 测试并发下载限制

#### 2. 错误处理测试
- 输入无效 URL
- 测试网络断开情况
- 验证不支持网站的处理
- 测试存储空间不足的情况

#### 3. 浏览器兼容性测试
- Chrome/Chromium 测试
- Firefox 测试
- Safari 测试
- 移动端浏览器测试

### 性能测试
- 大文件下载测试
- 高并发下载测试
- 长时间运行稳定性测试
- 内存使用监控

### 测试数据准备
推荐使用以下类型的测试链接：
- YouTube 短视频（<5分钟）
- YouTube 长视频（>30分钟）
- YouTube 播放列表（10-20个视频）
- 其他支持的网站链接
- 4K/8K 高清视频
- 直播流链接
- 用户提供的测试连接

### 测试报告
每次测试完成后记录：
- 测试环境信息
- 测试场景和步骤
- 发现的问题和错误
- 性能表现数据
- 浏览器兼容性情况