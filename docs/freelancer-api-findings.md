# Freelancer.com 官方 API 核验结论

核验日期：2026-07-21。以下结论只采用 Freelancer.com 官方开发者站点；未公开的限制不会被推测为已获授权。

## 结论摘要

1. **存在公开项目搜索接口。** `GET /api/projects/0.1/projects/active/` 用于搜索仍可投标的活跃项目，需要带有 `basic` scope 的 OAuth Token。它支持关键词、项目类型、预算、技能 Job ID、国家、语言、更新时间、排序、分页以及详情投影参数。
2. **存在项目详情接口。** `GET /api/projects/0.1/projects/{project_id}/` 返回指定项目，可请求完整描述、技能、雇主信息、雇主信誉、财务/验证信息等投影。
3. **存在官方 Bid 创建接口。** `POST /api/projects/0.1/bids/` 创建 Bid，请求体使用 Bid 结构，官方沙箱示例包含 `project_id`、`amount`、`period`、`bidder_id`、`milestone_percentage`；Bid 结构还支持 proposal/description。
4. **个人账号可以代表自己调用。** 官方 Personal Access Token 文档明确说明它适合“以自己身份发起认证请求”；官方沙箱文档演示个人 freelancer 账号生成 Token 后调用 Bid 接口。它并不保证任意账号都能成功投标，账号资料、技能、项目状态和平台业务规则仍会产生 400/403/409。
5. **认证方式。** API 使用 OAuth 2.0。访问 API 时通过 `Freelancer-OAuth-V1: <token>` 请求头传递 Token。Bid 创建需要 `basic` 和高级 scope `fln:project_manage`。只服务自己的程序可使用 Personal Access Token；代表其他用户时必须创建 OAuth Client，并等待 Freelancer 审核。
6. **Sandbox 与生产隔离。** Sandbox API 基地址是 `https://www.freelancer-sandbox.com/api`，生产是 `https://www.freelancer.com/api`。两边 Token 不互通；官方说明 Personal Access Token 每个环境只能同时有一个，生成后有效期为 30 天。Sandbox 可能被周期性重置，不保证数据持久化。
7. **限流规则按端点执行。** 官方通用文档未给活跃项目搜索或 Bid 创建一个固定的公开数字。客户端必须读取 `RateLimit-Limit` 与 `RateLimit-Remaining` 响应头，并处理 HTTP 429。官方示例展示了“每 60 秒 50 次、每 3600 秒 1000 次”的头格式，但这只是示例，不应当视为所有端点的承诺。本系统还额外设置每小时 2 次、每天 8 次 Bid 的本地安全上限。
8. **搜索结果字段。** 官方示例与参考文档显示可获得项目 ID、标题、预览/完整描述、预算、币种及汇率、项目类型、提交/更新时间、开放状态、SEO URL、技能/Job、已有 Bid 数及平均 Bid、升级标记、owner ID；通过投影可继续请求 owner/user 详情。
9. **雇主可信度信息可部分获取。** 项目接口支持 `owner_info`、`user_details`、`user_employer_reputation`、`user_employer_reputation_extra` 与 `user_financial_details` 等投影。因此评分、信誉细节和部分财务/验证状态可在权限与返回数据允许时取得。字段缺失时本系统记录为 unknown，不伪造为未验证或低评分。

## 对本项目实现的影响

- 项目抓取使用官方 Active Projects API，不进行网页抓取、Cookie 窃取、验证码绕过或浏览器模拟点击。
- 真实 Bid 客户端已实现，但默认 `FREELANCER_BID_SUBMISSION_ENABLED=false`。
- 真实提交需要：生产 Token、`fln:project_manage` 权限、项目仍开放、报价仍在范围内、Proposal 非空、未重复提交、用户先批准、再次输入 `SUBMIT` 确认、非 dry-run、未超过本地小时/每日上限。
- 如果实际 Token/账号收到 403 或缺少 scope，系统记录失败并引导使用原始项目链接手动投标，不尝试规避平台控制。
- Personal Access Token 有 30 天有效期，部署运维必须包含定期轮换。

## 官方来源

- [Search for Active Projects / Project reference](https://developers.freelancer.com/docs/projects/projects#projects-get-3)
- [Get Project by ID](https://developers.freelancer.com/docs/projects/projects#projects-get-2)
- [Create a Bid](https://developers.freelancer.com/docs/projects/bids#bids-post)
- [Bidding on a Project use case](https://developers.freelancer.com/docs/use-cases/bidding-on-a-project)
- [Authentication with OAuth](https://developers.freelancer.com/docs/authentication/authentication-with-oauth)
- [Creating a Client](https://developers.freelancer.com/docs/authentication/creating-a-client)
- [Advanced Scopes](https://developers.freelancer.com/docs/authentication/advanced-scopes)
- [Personal Access Tokens](https://developers.freelancer.com/docs/authentication/personal-access-tokens)
- [Using Access Tokens](https://developers.freelancer.com/docs/authentication/using-access-tokens)
- [Sandbox Environment](https://developers.freelancer.com/docs/api-overview/sandbox-environment)
- [Rate Limiting](https://developers.freelancer.com/docs/api-overview/rate-limiting)

