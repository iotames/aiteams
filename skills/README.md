# Skills 技能库

本目录集中存放本项目的技能（Skill）——每个技能是一个带 `SKILL.md` 的文件夹，SKILL.md 是写给 AI 使用的说明书，定义了技能的用途、触发条件、使用方法和注意事项。

## 技能一览

| 技能 | 一句话简介 | 典型使用场景 |
|---|---|---|
| [chromedp](chromedp/) | 通过 Chrome DevTools Protocol (CDP) 控制系统已安装的 Chrome/Edge 进行浏览器调试 | 「截图看看」「检查 JS 错误」「提取页面文字」「验证接口」、填写表单、点击按钮、检查网络请求等浏览器自动化与 debug 操作 |
| [capture-hls-video](capture-hls-video/) | 抓取网页里正在播放的加密 HLS 视频并归档成 MP4（注入钩子拿真实解密 key、并发下载分片、AES-128 解密、转封装） | 网页视频没有下载按钮时保存课程回放 / 点播 / 直播回放；涉及 m3u8、blob: 视频源、HLS AES-128 加密、hls.js / tcplayer / 腾讯云 VOD 的场景。仅限有权访问且有权留存的内容 |
| [flipbook-download](flipbook-download/) | 下载网页版翻页画册 / 电子画册 / 产品目录（flipbook） | 网页没有下载按钮时，抓取 Heyzine、FlipHTML5、FlipBuilder 等平台的画册，自动识别平台、定位源文件（优先 PDF 直链）并完整下载 |
| [routerman](routerman/) | 登录 ZTE 路由器管理后台并执行常用管理操作 | 「端口转发 / 端口映射 / 开端口」「父母控制 / 限制上网」「URL 黑名单 / 白名单」等路由器配置的增删改查，通过 HTTP API 直接完成，无需浏览器自动化 |
| [skill-creator](skill-creator/) | 创建新技能、修改优化已有技能、运行评测与分析 | 从零创建技能、优化技能描述以提高触发准确率、运行测试评测与基准对比、「怎么写 SKILL.md」等问题 |

## 技能依赖关系

部分技能之间存在依赖，安装前请先确认前置技能：

```
flipbook-download
└── chromedp（前置技能，提供 CDP 浏览器控制）
    └── Python 3.7+ / websocket-client

capture-hls-video
└── chromedp（前置技能，提供 CDP 浏览器控制）
    ├── Python 3.10+ / websocket-client / cryptography
    └── ffmpeg（必需）、aria2c（可选，未装则回退内置并发下载）
```

## 使用方式

每个技能的具体用法见其对应文件夹内的 `SKILL.md`。技能需要先安装到 Reasonix 才能被触发，安装与卸载详见 `install-capability` 能力。

## 新增技能

需要新增技能时，推荐使用 [skill-creator](skill-creator/) 技能，或参考已有技能目录结构：

```
skill-name/
├── SKILL.md      # 技能说明（必填：name + description 元信息）
├── scripts/      # 实现脚本
├── references/   # 可选参考资料（按需加载，供 SKILL.md 指路）
└── assets/       # 可选输出资源（模板、图标等）
```
