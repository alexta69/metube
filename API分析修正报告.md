# tingdao.org API分析修正报告

## 审核员反馈确认

根据审核员对提交 167a843 的审核意见，我承认初步分析存在以下重大遗漏：

### ❌ 初步分析的错误和遗漏

1. **API端点识别错误**
   - ❌ 错误：认为 `/Record/is_voi` 是获取音频信息的主要API
   - ✅ 正确：`/Record/exhibitions` 负责返回系列信息
   - ✅ 正确：`/Record/is_voi` 仅用于标记收藏状态（需cookie uid，但可留空）

2. **数据结构分析不足**
   - ❌ 遗漏：没有发现 mediaList 播放列表结构
   - ❌ 遗漏：未分析重要字段含义
   - ✅ 需补充：videos_url（备用源）、add_time（发布时间）等字段

3. **yt-dlp开发规范不完整**
   - ❌ 遗漏：_TESTS 测试用例定义
   - ❌ 遗漏：_extractors.py 更新要求
   - ❌ 遗漏：POST请求的headers/data格式规范

4. **Metube部署方案不具体**
   - ❌ 模糊：部署自定义extractor的具体方式
   - ✅ 需明确：升级/自编译yt-dlp vs 插件目录方案

## 重新调研发现

### 🔍 正在进行的深入API分析

#### 当前已确认信息：
- **测试页面**：`https://www.tingdao.org/dist/#/Media?device=mobile&id=11869`
- **媒体ID**：`11869`
- **播放列表**：包含8个音频项目
- **当前音频URL**：`http://1256958968.vod2.myqcloud.com/.../音频.mp3?签名参数`

#### 页面结构分析：
```
播放列表结构：
1. 2018年10月 柏训师生会：神永远的旨意-基督与教会 01 于宏洁
2. 2018年10月 柏训师生会：神永远的旨意-基督与教会 02 于宏洁
3. 2018年10月 柏训师生会：神永远的旨意-基督与教会 03 我们的使命：称为耶稣基督道成肉身的见证人 于宏洁
4. 2018年10月 柏训师生会：神永远的旨意-基督与教会 04 异象与使命的落实：VIP模式 于宏洁
5. 2018年10月 柏训师生会：神永远的旨意-基督与教会 05 异象与使命的落实：本于祂，倚靠祂，归于祂 于宏洁
6. 2018年10月 柏训师生会：神永远的旨意-基督与教会 06 异象与使命的落实：同一心灵，同一脚踪 于宏洁
7. 2018年10月 柏训师生会：神永远的旨意-基督与教会 07 异象与使命的落实：成全圣徒，各尽其职 于宏洁
8. 2018年10月 柏训师生会：神永远的旨意-基督与教会 08 异象与使命的落实：凡事长进，连于元首基督 于宏洁
```

#### 网络请求监控结果：
- 已设置全面的 Fetch 和 XHR 监控
- 正在测试 `/Record/exhibitions` 端点
- 同时验证 `/Record/is_voi` 的收藏功能

## 修正后的技术方案框架

### 1. 正确的API调用逻辑
```python
# 主要API：获取播放列表信息
exhibitions_url = 'https://www.tingdao.org/Record/exhibitions'
exhibitions_data = self._download_json(
    exhibitions_url,
    media_id,
    data=f'id={media_id}'.encode(),
    headers={'Content-Type': 'application/x-www-form-urlencoded'}
)

# 解析 mediaList 结构
for item in exhibitions_data.get('mediaList', []):
    # 提取完整字段信息
    entry = {
        'id': item['id'],
        'title': item['title'],
        'url': item['video_url'],        # 主要音频源
        'alt_url': item['videos_url'],   # 备用音频源
        'timestamp': item['add_time'],   # 发布时间
        'thumbnail': item.get('img_url'),
        'ext': 'mp3'
    }
```

### 2. yt-dlp开发Checklist
基于官方CONTRIBUTING.md：

#### ✅ 必需组件：
- [ ] `_VALID_URL` 正则匹配
- [ ] `_TESTS` 至少一个测试用例
- [ ] `_real_extract()` 核心提取方法
- [ ] 更新 `yt_dlp/extractor/_extractors.py`
- [ ] 通过 `hatch test TingdaoIE` 测试
- [ ] 通过 `hatch fmt --check` 代码检查

#### ✅ _TESTS 标准格式：
```python
_TESTS = [{
    'url': 'https://www.tingdao.org/dist/#/Media?device=mobile&id=11869',
    'info_dict': {
        'id': '11869',
        'title': '2018年10月 柏训师生会：神永远的旨意-基督与教会',
        'ext': 'mp3',
    },
    'playlist_count': 8,
    'params': {
        'skip_download': True,  # 用于CI测试
    }
}]
```

### 3. Metube部署方案

#### 方案A：yt-dlp插件系统（推荐）
```bash
# 1. 创建插件目录结构
~/.config/yt-dlp/plugins/tingdao_plugin/
└── yt_dlp_plugins/
    └── extractor/
        └── tingdao.py

# 2. Docker volume挂载
volumes:
  - "./plugins:/app/.config/yt-dlp/plugins"
```

#### 方案B：自编译yt-dlp
- Fork yt-dlp仓库
- 添加extractor到官方目录
- 重新构建Metube Docker镜像

#### 方案C：升级yt-dlp版本
- 等待官方接受PR
- 使用标准yt-dlp更新

## 下一步深入调研计划

### 阶段1：完成API端点验证
- [ ] 确认 `/Record/exhibitions` 完整响应格式
- [ ] 验证 mediaList 数据结构和所有字段
- [ ] 测试 `/Record/is_voi` 收藏功能机制
- [ ] 分析音频URL签名和有效期机制

### 阶段2：extractor实现设计
- [ ] 基于真实API设计URL匹配规则
- [ ] 实现单音频和播放列表支持
- [ ] 添加备用源和错误处理
- [ ] 编写完整的测试用例

### 阶段3：集成测试验证
- [ ] 本地yt-dlp测试
- [ ] Metube集成测试
- [ ] 浏览器功能验证
- [ ] 性能和稳定性测试

## 待审核员确认的问题

1. **API调研重点**：是否重点关注exhibitions端点的完整响应结构？
2. **实现优先级**：单音频支持 vs 完整播放列表支持的开发顺序？
3. **部署策略**：更倾向于插件方式还是官方PR方式？
4. **测试范围**：除了当前测试URL，是否需要发现更多测试用例？

---

**报告时间**：2025-09-23
**状态**：API深入调研进行中
**下一步**：基于审核员指导继续API端点验证