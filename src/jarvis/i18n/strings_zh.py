"""Chinese (zh) string table for JARVIS."""

STRINGS: dict[str, str] = {
    # ── System ──────────────────────────────────────────────────────────
    "system.name": "JARVIS",
    "system.version": "v0.2.0",
    "system.welcome": "JARVIS -- 您的个人AI助手，欢迎使用",
    "system.goodbye": "再见！",
    "system.initializing": "正在初始化 JARVIS...",
    "system.ready": "系统就绪：{agent_count} 个智能体，{tool_count} 个工具",
    "system.shutting_down": "正在关闭...",
    "system.uptime": "运行时间：{hours}小时 {minutes}分钟",
    "system.version_info": "JARVIS {version}（Python {python_version}）",
    "system.update_available": "有新版本可用：{new_version}",

    # ── Agents ──────────────────────────────────────────────────────────
    "agent.registered": "智能体 '{name}' 已注册",
    "agent.not_found": "未找到智能体 '{name}'",
    "agent.routing_to": "路由至 '{name}'（置信度={score}）",
    "agent.no_handler": "没有智能体可以处理此请求",
    "agent.execution_failed": "智能体 '{name}' 执行失败：{error}",
    "agent.execution_started": "智能体 '{name}' 开始处理",
    "agent.execution_completed": "智能体 '{name}' 在 {duration}ms 内完成",
    "agent.idle": "智能体 '{name}' 空闲中",
    "agent.busy": "智能体 '{name}' 忙碌中",
    "agent.shutdown": "智能体 '{name}' 已关闭",
    "agent.code.description": "代码审查、代码生成、Git 操作和构建管理",
    "agent.knowledge.description": "信息检索、文档问答和知识图谱查询",
    "agent.calendar.description": "日程管理、冲突检测和会议准备",
    "agent.comms.description": "邮件分类、消息摘要、回复草稿和通知管理",
    "agent.ops.description": "监控、告警诊断、部署和事故响应",
    "agent.data.description": "数据分析、统计、可视化和数据转换",
    "agent.security.description": "安全审计、漏洞扫描和合规检查",
    "agent.devops.description": "Docker、Kubernetes、CI/CD 和基础设施管理",
    "agent.writing.description": "技术写作、文档编写和内容创作",
    "agent.research.description": "深度研究、分析和报告生成",

    # ── Specs ───────────────────────────────────────────────────────────
    "spec.created": "已创建 Streaming Spec：{id}",
    "spec.executing": "正在执行规格 '{name}'...",
    "spec.completed": "规格已完成：{progress}",
    "spec.failed": "规格执行失败：{error}",
    "spec.paused": "规格已暂停",
    "spec.resumed": "规格已恢复",
    "spec.cancelled": "规格已取消",
    "spec.redirected": "规格已重定向至：{intent}",
    "spec.step.pending": "等待中",
    "spec.step.ready": "就绪",
    "spec.step.blocked": "已阻塞（等待依赖）",
    "spec.step.executing": "执行中...",
    "spec.step.completed": "已完成",
    "spec.step.failed": "已失败",
    "spec.step.skipped": "已跳过",
    "spec.step.cancelled": "已取消",
    "spec.constraint.added": "已添加约束：{content}",
    "spec.constraint.removed": "已移除约束",
    "spec.constraint.modified": "已修改约束",
    "spec.dag.valid": "DAG 验证通过",
    "spec.dag.cycle_detected": "依赖图中检测到环",
    "spec.progress": "进度：{done}/{total}（{pct}%）",

    # ── Tools ───────────────────────────────────────────────────────────
    "tool.registered": "工具 '{name}' 已注册",
    "tool.not_found": "未找到工具 '{name}'",
    "tool.execution.success": "工具 '{name}' 执行成功",
    "tool.execution.failed": "工具 '{name}' 执行失败：{error}",
    "tool.execution.timeout": "工具 '{name}' 在 {seconds}s 后超时",
    "tool.blocked": "命令因安全原因被阻止：{reason}",
    "tool.approval_required": "工具 '{name}' 需要人工审批",
    "tool.approved": "工具 '{name}' 已批准",
    "tool.denied": "工具 '{name}' 已拒绝",

    # ── Memory ──────────────────────────────────────────────────────────
    "memory.added": "已添加记忆（重要性={importance}）",
    "memory.updated": "记忆已更新：{id}",
    "memory.deleted": "记忆已删除：{id}",
    "memory.search.results": "找到 {count} 条相关记忆",
    "memory.search.empty": "未找到匹配的记忆",
    "memory.pruned": "已清理 {count} 条过期记忆",
    "memory.capacity": "记忆使用量：{used}/{total}",

    # ── Knowledge ───────────────────────────────────────────────────────
    "knowledge.extracted": "已提取 {count} 个实体",
    "knowledge.query.results": "找到 {count} 个相关节点",
    "knowledge.saved": "知识图谱已保存（{nodes} 个节点，{edges} 条边）",
    "knowledge.loaded": "知识图谱已加载（{nodes} 个节点，{edges} 条边）",
    "knowledge.node.added": "已添加节点：{label}",
    "knowledge.edge.added": "已添加边：{source} -> {target}",

    # ── Skills ──────────────────────────────────────────────────────────
    "skill.distilled": "已从规格中提炼技能：{name}",
    "skill.evolved": "技能已进化：{name} v{version}",
    "skill.loaded": "已加载 {count} 个技能",
    "skill.applied": "技能已应用：{name}",
    "skill.not_found": "未找到技能 '{name}'",

    # ── Curator ─────────────────────────────────────────────────────────
    "curator.approved": "审查：已通过（评分={score}）",
    "curator.needs_revision": "审查：需要修改（评分={score}）",
    "curator.rejected": "审查：已拒绝（评分={score}）",
    "curator.flagged": "审查：已标记为需人工审查",
    "curator.reviewing": "正在审查输出...",

    # ── Security ────────────────────────────────────────────────────────
    "security.permission.denied": "权限被拒绝：{resource}（{level}）",
    "security.permission.granted": "权限已授予：{resource}",
    "security.secret.detected": "检测到潜在密钥并已脱敏",
    "security.command.blocked": "命令被沙箱阻止：{command}",
    "security.audit.logged": "安全事件已记录：{event}",

    # ── Errors ──────────────────────────────────────────────────────────
    "error.general": "发生错误：{message}",
    "error.timeout": "操作在 {seconds}s 后超时",
    "error.rate_limited": "超出速率限制，请稍后再试。",
    "error.not_found": "未找到 {resource}",
    "error.validation": "验证错误：{details}",
    "error.connection": "连接错误：{details}",
    "error.auth": "认证失败：{details}",
    "error.permission": "权限被拒绝：{details}",
    "error.internal": "内部错误：{message}",

    # ── CLI ──────────────────────────────────────────────────────────────
    "cli.help": "输入 'help' 查看可用命令",
    "cli.unknown_command": "未知命令：{command}",
    "cli.confirm_exit": "退出 JARVIS？",
    "cli.prompt": "jarvis> ",
    "cli.processing": "处理中...",
    "cli.done": "完成。",

    # ── Notifications ───────────────────────────────────────────────────
    "notification.sent": "通知已发送：{title}",
    "notification.quiet_hours": "通知已抑制（静默时段）",
    "notification.rate_limited": "通知频率受限",
    "notification.channel.not_found": "未找到通知渠道 '{channel}'",

    # ── Diagnostics ─────────────────────────────────────────────────────
    "diagnostics.running": "正在运行系统诊断...",
    "diagnostics.completed": "诊断完成：{status}",
    "diagnostics.check.passed": "{name}：通过",
    "diagnostics.check.failed": "{name}：失败",

    # ── Benchmarks ──────────────────────────────────────────────────────
    "benchmark.running": "正在运行基准测试（{iterations} 次迭代）...",
    "benchmark.completed": "基准测试完成：{count} 项测试",
    "benchmark.result": "{name}：{ops_per_sec} 次/秒（平均={avg_ms}ms）",

    # ── MCP ──────────────────────────────────────────────────────────────
    "mcp.server.started": "MCP 服务器已启动于 {host}:{port}",
    "mcp.server.stopped": "MCP 服务器已停止",
    "mcp.tool.called": "MCP 工具调用：{name}",
    "mcp.resource.accessed": "MCP 资源访问：{uri}",

    # ── Workflow ─────────────────────────────────────────────────────────
    "workflow.started": "工作流已启动：{name}",
    "workflow.completed": "工作流已完成：{name}",
    "workflow.failed": "工作流失败：{name}（{error}）",
    "workflow.step.started": "工作流步骤已开始：{step}",
    "workflow.step.completed": "工作流步骤已完成：{step}",
}
