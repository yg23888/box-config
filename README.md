# box-config

FongMi/TV（影视TV）与 TVBox 兼容播放器使用的公开配置仓库。每 7 天自动合并一次公开源，校验后发布。

## 订阅地址

核心配置（默认使用，仅数据型 API 源）：

```
https://cdn.jsdelivr.net/gh/yg23888/box-config@main/core.json
```

备用地址（GitHub 直连）：

```
https://raw.githubusercontent.com/yg23888/box-config/main/core.json
```

扩展包（JS 源，默认不启用，见下方安全说明）：

```
https://cdn.jsdelivr.net/gh/yg23888/box-config@main/ext.json
```

## 文件说明

| 文件 | 内容 |
|---|---|
| `core.json` | 69 个数据型站点（type 0/1）、67 个解析、42 个直播源 |
| `ext.json` | 8 个 JS 源（type 3，仅 HTTPS），默认不加载 |
| `manifest.json` | 生成时间、文件 SHA-256、各源抓取状态、JS 源哈希 |
| `core.prev.json` | 上一版核心配置，用于回滚 |
| `merge_config.py` | 合并与校验脚本（仅 Python 标准库） |

## 更新机制

- GitHub Actions 每周一 03:00（北京时间）自动运行，也可在 Actions 页面手动触发。
- 合并后校验：至少 4 个源可达、核心站点 ≥ 45、较上一版跌幅不得超过 20%、ext 只允许 HTTPS。
- 任一校验失败：**不写入、不提交**，仓库保留上一版。
- 提交前自动把旧版保存为 `core.prev.json`。

## 安全边界

- `core.json` 只包含返回 JSON/XML 的 API 源，播放器只解析数据，不执行代码。
- `ext.json` 包含 JavaScript 源，属于**可执行远程代码**，因此：
  - 默认不加载，需要手动添加；
  - 只接受 HTTPS；
  - `manifest.json` 记录每个 JS 的 SHA-256，客户端可校验后再执行；
  - 只建议在 QuickJS 运行时下使用，不要给不可信源开启 Node/Python 运行时。
- 核心配置中允许存在 `http://` 的 API 源（仅数据传输，不执行代码），但这些条目在清单中可辨识；如追求全链路加密，可在 `merge_config.py` 中把 core 也改为 HTTPS-only。

## 在 FongMi/TV 中使用

设置 → 点播 → 添加配置，粘贴上面的 `core.json` 地址即可。扩展包按需单独添加。

## 免责声明

本仓库只做公开配置的聚合与去重，不存储、不分发任何影视内容。所有源均来自第三方公开地址，可用性与合法性由源站负责。
