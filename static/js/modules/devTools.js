/**
 * 开发者工具模块
 * 负责Cookie格式转换等功能 - 流式输出版本
 */

// 存储当前的AbortController用于取消请求
let currentAbortController = null;
let isGenerating = false;

/**
 * 生成Netscape格式cookies - 真流式输出
 */
async function generateNetscapeCookies() {
    // 如果正在生成，则停止
    if (isGenerating) {
        stopGeneration();
        return;
    }
    const inputText = document.getElementById('cookiesInput');
    
    if (!inputText) {
        console.error('找不到cookiesInput元素');
        return;
    }
    
    const cookieText = inputText.value.trim();
    
    if (!cookieText) {
        alert('请输入Cookie内容');
        return;
    }
    
    // 隐藏空状态，显示输出区域
    document.getElementById('devToolsEmptyState').style.display = 'none';
    const outputArea = document.getElementById('devToolsOutputArea');
    outputArea.style.display = 'block';
    outputArea.textContent = '正在转换...'; // 提示正在处理
    
    // 隐藏复制按钮
    document.getElementById('devToolsCopyBtn').style.display = 'none';
    
    try {
        // 创建新的AbortController
        currentAbortController = new AbortController();
        isGenerating = true;
        
        // 更新按钮状态为"停止生成"
        const btn = document.getElementById('generateCookiesBtn');
        const btnIcon = document.getElementById('generateCookiesBtnIcon');
        const btnText = document.getElementById('generateCookiesBtnText');
        
        btnIcon.className = 'fas fa-stop';
        btnText.textContent = '停止生成';
        btnText.setAttribute('data-zh', '停止生成');
        btnText.setAttribute('data-en', 'Stop');
        btn.style.background = 'linear-gradient(135deg, rgba(248, 113, 113, 0.9) 0%, rgba(239, 68, 68, 0.9) 100%)';
        
        // 使用流式API
        const response = await fetch('/api/dev-tools/generate-cookies-stream', {
            signal: currentAbortController.signal,
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ cookies_text: cookieText })
        });
        
        if (!response.ok) {
            throw new Error('转换失败');
        }
        
        // 初始化，清空之前的内容
        outputArea.textContent = '';
        window.generatedNetscapeCookies = '';
        
        // 读取流式响应
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        
        let buffer = ''; // 缓冲区，处理不完整的行
        
        while (true) {
            const { done, value } = await reader.read();
            
            if (done) {
                console.log('流结束，最终内容长度:', window.generatedNetscapeCookies.length);
                console.log('输出区域内容长度:', outputArea.textContent.length);
                break;
            }
            
            // 解码新数据并添加到缓冲区
            buffer += decoder.decode(value, { stream: true });
            
            // 按行处理
            const lines = buffer.split('\n');
            // 保留最后一个可能不完整的行
            buffer = lines.pop() || '';
            
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.substring(6));
                        
                        if (data.error) {
                            throw new Error(data.error);
                        }
                        
                        if (data.content) {
                            // 实时追加内容到全局变量和显示区域
                            window.generatedNetscapeCookies += data.content;
                            outputArea.textContent += data.content;
                            // 自动滚动到底部
                            outputArea.scrollTop = outputArea.scrollHeight;
                            console.log('收到内容片段，当前总长度:', window.generatedNetscapeCookies.length);
                        }
                        
                        if (data.done) {
                            // 转换完成，显示复制按钮
                            document.getElementById('devToolsCopyBtn').style.display = 'flex';
                            console.log('✅ 转换完成，最终内容长度:', window.generatedNetscapeCookies.length);
                            console.log('✅ 输出区域长度:', outputArea.textContent.length);
                        }
                    } catch (e) {
                        console.error('解析SSE数据失败:', e, '原始行:', line);
                    }
                }
            }
        }
        
        // 流结束后再次确认内容
        console.log('🎯 流式接收完成');
        console.log('🎯 全局变量长度:', window.generatedNetscapeCookies.length);
        console.log('🎯 DOM元素长度:', outputArea.textContent.length);
        
    } catch (error) {
        if (error.name === 'AbortError') {
            console.log('用户取消了生成');
            alert('已停止生成');
        } else {
            console.error('转换失败:', error);
            alert('转换失败: ' + error.message);
        }
        outputArea.style.display = 'none';
        document.getElementById('devToolsEmptyState').style.display = 'flex';
    } finally {
        // 重置状态
        isGenerating = false;
        currentAbortController = null;
        
        // 恢复按钮状态
        const btn = document.getElementById('generateCookiesBtn');
        const btnIcon = document.getElementById('generateCookiesBtnIcon');
        const btnText = document.getElementById('generateCookiesBtnText');
        
        btnIcon.className = 'fas fa-magic';
        btnText.textContent = '生成Netscape格式';
        btnText.setAttribute('data-zh', '生成Netscape格式');
        btnText.setAttribute('data-en', 'Generate Netscape Format');
        btn.style.background = 'linear-gradient(135deg, rgba(20, 20, 20, 0.95) 0%, rgba(30, 30, 30, 0.95) 100%)';
    }
}

/**
 * 停止生成
 */
function stopGeneration() {
    if (currentAbortController) {
        currentAbortController.abort();
    }
}

/**
 * 复制Netscape格式cookies
 */
async function copyNetscapeCookies() {
    if (!window.generatedNetscapeCookies) {
        alert('没有可复制的内容');
        return;
    }
    
    try {
        // 创建临时textarea元素进行复制
        const textarea = document.createElement('textarea');
        textarea.value = window.generatedNetscapeCookies;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        
        const successful = document.execCommand('copy');
        document.body.removeChild(textarea);
        
        if (successful) {
            // 显示成功提示（3秒后自动消失）
            const btn = document.getElementById('devToolsCopyBtn');
            const originalHTML = btn.innerHTML;
            btn.innerHTML = '<i class="fas fa-check" style="margin-right: 8px;"></i><span>已复制</span>';
            btn.style.background = 'linear-gradient(135deg, rgba(34, 197, 94, 0.9) 0%, rgba(22, 163, 74, 0.9) 100%)';
            
            setTimeout(() => {
                btn.innerHTML = originalHTML;
            }, 2000);
        } else {
            throw new Error('复制命令执行失败');
        }
    } catch (error) {
        console.error('复制失败:', error);
        alert('复制失败，请手动选择并复制');
    }
}

console.log('✅ 开发者工具模块已加载');
