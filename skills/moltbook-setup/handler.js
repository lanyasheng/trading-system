const path = require('path');

module.exports = async function({ message, tools }) {
    const text = (message.content || '').trim();

    const setupMatch = text.match(/Set up my email for Moltbook login:\s*([^\s]+)|setup-moltbook\s+([^\s]+)/i);
    if (setupMatch) {
        const email = setupMatch[1] || setupMatch[2];
        const emailRegexSimple = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegexSimple.test(email)) {
            return "❌ 邮箱格式不正确，请提供有效邮箱地址。";
        }
        const scriptPath = path.join(__dirname, 'scripts', 'setup_owner_email.sh');
        const command = `bash ${JSON.stringify(scriptPath)} ${JSON.stringify(email)}`;
        const response = await tools.exec({ command, timeout: 15000, silent: true });
        const statusMatch = response.match(/HTTP_STATUS:(\d{3})/);
        const statusCode = statusMatch ? Number(statusMatch[1]) : 0;

        if (statusCode >= 200 && statusCode < 300) {
            return `✅ 已发送验证邮件至 ${email}。请查收邮件并完成验证。`;
        }
        if (response.includes('Agent must be claimed first')) {
            return `⚠️ 当前 Moltbook agent 还未完成 claim。请先打开 claim 链接完成邮箱+X 验证，再重试。`;
        }
        if (response.includes('MOLTBOOK_API_KEY is not set')) {
            return `⚠️ 未检测到 Moltbook API key。请设置 MOLTBOOK_API_KEY 或 ~/.openclaw/credentials/moltbook_api_key。`;
        }
        return `⚠️ 设置失败，请稍后重试。\n${response.slice(0, 400)}`;
    }

    if (/^(moltbook-status|check-moltbook-status)$/i.test(text)) {
        const scriptPath = path.join(__dirname, 'scripts', 'check_status.sh');
        const response = await tools.exec({ command: `bash ${JSON.stringify(scriptPath)}`, timeout: 15000, silent: true });
        if (response.includes('"status":"claimed"')) return '✅ Moltbook 状态：claimed（已认领可用）。';
        if (response.includes('"status":"pending_claim"')) return '⚠️ Moltbook 状态：pending_claim（需先完成 claim）。';
        return `ℹ️ 状态查询结果：\n${response.slice(0, 500)}`;
    }

    const postMatch = text.match(/^moltbook-post\s+([^|]+)\|([^|]+)\|([\s\S]+)$/i);
    if (postMatch) {
        const submolt = postMatch[1].trim();
        const title = postMatch[2].trim();
        const content = postMatch[3].trim();
        if (!title || !content) return '❌ 发帖参数不足。用法: moltbook-post <submolt>|<title>|<content>';

        const scriptPath = path.join(__dirname, 'scripts', 'create_post.sh');
        const cmd = `bash ${JSON.stringify(scriptPath)} ${JSON.stringify(submolt)} ${JSON.stringify(title)} ${JSON.stringify(content)}`;
        const response = await tools.exec({ command: cmd, timeout: 20000, silent: true });
        const ok = /HTTP_STATUS:2\d\d/.test(response);
        if (ok) return `✅ Moltbook 发帖成功：${title}`;
        if (response.includes('pending_claim') || response.includes('must be claimed')) return '⚠️ 发帖失败：agent 未完成 claim。';
        return `⚠️ 发帖失败：\n${response.slice(0, 500)}`;
    }

    return "可用命令：\n1) setup-moltbook your@email.com\n2) moltbook-status\n3) moltbook-post submolt|标题|正文";
};
