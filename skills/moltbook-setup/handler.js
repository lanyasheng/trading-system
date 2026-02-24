const path = require('path');

module.exports = async function({ message, env, tools }) {
    // 解析邮箱
    const emailRegex = /Set up my email for Moltbook login:\s*([^\s]+)|setup-moltbook\s+([^\s]+)/i;
    const emailMatch = message.content.match(emailRegex);
    
    if (!emailMatch) {
        return "❌ 请提供邮箱地址。用法：\n- Set up my email for Moltbook login: your@email.com\n- setup-moltbook your@email.com";
    }
    
    const email = emailMatch[1] || emailMatch[2];
    
    // 验证邮箱格式
    const emailRegexSimple = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegexSimple.test(email)) {
        return "❌ 邮箱格式不正确，请提供有效邮箱地址。";
    }
    
    try {
        const scriptPath = path.join(__dirname, 'scripts', 'setup_owner_email.sh');
        const command = `bash ${JSON.stringify(scriptPath)} ${JSON.stringify(email)}`;
        const response = await tools.exec({
            command,
            timeout: 15000,
            silent: true
        });

        const statusMatch = response.match(/HTTP_STATUS:(\d{3})/);
        const statusCode = statusMatch ? Number(statusMatch[1]) : 0;

        if (statusCode >= 200 && statusCode < 300) {
            return `✅ 已发送验证邮件至 ${email}！\\n\\n请查收邮件并点击链接完成 X 验证。\\n\\n验证完成后，您就可以在 https://moltbook.com/login 登录了。`;
        }

        if (response.includes('Agent must be claimed first')) {
            return `⚠️ 当前 Moltbook agent 还未完成认领（claim），所以暂时不能直接发登录邮件。\\n\\n请先完成 claim 页面里的邮箱验证 + X 验证，然后再执行：\\nsetup-moltbook ${email}`;
        }

        if (response.includes('MOLTBOOK_API_KEY is not set')) {
            return `⚠️ 未检测到 Moltbook API key。\\n请设置环境变量 MOLTBOOK_API_KEY，或将 key 写入 ~/.openclaw/credentials/moltbook_api_key`;
        }

        {
            return `⚠️ 设置过程中遇到问题。请检查：\\n- 您的 bot 是否已连接到 Moltbook\\n- 邮箱是否正确\\n\\n如问题持续，请手动访问 https://moltbook.com/login 并输入邮箱。`;
        }
        
    } catch (error) {
        console.error('Moltbook setup error:', error);
        
        // 如果 API 调用失败，提供备选方案
        if (error.message.includes('ECONNREFUSED') || error.message.includes('timeout')) {
            return `⚠️ API 调用失败。请尝试以下手动步骤：\\n\\n1. 访问 https://moltbook.com/login\\n2. 输入邮箱：${email}\\n3. 点击 "Send Login Link"\\n4. 查收邮件并完成验证`;
        } else {
            return `❌ 设置失败：${error.message}\\n\\n请稍后重试或联系管理员。`;
        }
    }
};
