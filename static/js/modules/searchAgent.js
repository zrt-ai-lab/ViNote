/**
 * AI视频搜索Agent模块
 * 处理对话式视频搜索和自动笔记生成
 */

// 会话管理
let agentSessionId = null;
let conversationHistory = [];
let currentSearchResults = [];
let isProcessing = false;

/**
 * 初始化搜索Agent
 */
function initSearchAgent() {
    agentSessionId = generateSessionId();
    currentSearchResults = [];
    isProcessing = false;
    
    // 清空UI，重新显示欢迎消息
    const container = document.getElementById('agentMessagesContainer');
    if (container) {
        container.innerHTML = '';
        showAgentWelcomeMessage();
    }
    
    console.log('搜索Agent已初始化, SessionID:', agentSessionId);
}

/**
 * 显示欢迎消息
 */
function showAgentWelcomeMessage() {
    const container = document.getElementById('agentMessagesContainer');
    container.innerHTML = '';
    
    const welcomeDiv = document.createElement('div');
    welcomeDiv.className = 'message message-ai';
    welcomeDiv.innerHTML = `
        <div class="message-avatar">
            <img src="/static/product-logo.png" alt="ViNote" style="width: 100%; height: 100%; object-fit: contain; border-radius: 50%;">
        </div>
        <div class="message-content">
            <div class="message-bubble">
                <p style="margin-bottom: 12px;">👋 您好!我是<strong>ViNote</strong> AI视频搜索助手。</p>
                <p style="margin-bottom: 12px;">我可以帮您:</p>
                <ul style="margin: 0; padding-left: 20px;">
                    <li>🔍 搜索各平台的优质视频</li>
                    <li>📝 自动生成视频笔记和摘要</li>
                    <li>💬 回答视频内容相关问题</li>
                </ul>
                <p style="margin-top: 12px; margin-bottom: 0;">告诉我您想学习什么内容,我来帮您找到最合适的视频!</p>
            </div>
        </div>
    `;
    
    container.appendChild(welcomeDiv);
}

/**
 * 发送Agent消息
 */
async function sendAgentMessage() {
    if (isProcessing) {
        showMessage('请等待当前任务完成', 'info');
        return;
    }
    
    const input = document.getElementById('agentInput');
    const message = input.value.trim();
    
    if (!message) return;
    
    // 显示用户消息
    appendUserMessage(message);
    input.value = '';
    
    // 标记处理中
    isProcessing = true;
    
    // 显示加载状态
    showAgentTyping();
    
    try {
        await streamAgentResponse(message);
    } catch (error) {
        console.error('Agent响应失败:', error);
        hideAgentTyping();
        appendErrorMessage('处理失败: ' + error.message);
    } finally {
        isProcessing = false;
    }
}

/**
 * 流式接收Agent响应
 */
async function streamAgentResponse(message) {
    const response = await fetch('/api/search-agent-chat', {
        method: 'POST',
        headers: { 
            'Content-Type': 'application/json',
            'Accept': 'text/event-stream'
        },
        body: JSON.stringify({
            session_id: agentSessionId,
            message: message
        })
    });
    
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    
    let currentMessageDiv = null;
    let buffer = '';
    
    try {
        while (true) {
            const { done, value } = await reader.read();
            
            if (done) {
                console.log('流式响应完成');
                break;
            }
            
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';
            
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        
                        // 首次收到消息时创建消息容器
                        if (!currentMessageDiv && data.type !== 'done') {
                            hideAgentTyping();
                            currentMessageDiv = createAgentMessageDiv();
                        }
                        
                        // 处理消息
                        if (data.type === 'done') {
                            console.log('消息流结束');
                        } else {
                            handleAgentMessage(data, currentMessageDiv);
                        }
                    } catch (e) {
                        console.error('解析消息失败:', e, line);
                    }
                }
            }
        }
    } finally {
        hideAgentTyping();
    }
}

/**
 * 处理不同类型的Agent消息
 */
function handleAgentMessage(data, messageDiv) {
    if (!messageDiv) return;
    
    switch (data.type) {
        case 'generation_id':
            // 保存生成任务ID
            currentGenerationId = data.generation_id;
            console.log('收到生成任务ID:', currentGenerationId);
            break;
            
        case 'text_chunk':
            // 流式文本块
            appendTextToAgentMessage(messageDiv, data.content);
            break;
        
        case 'thinking':
            // 思维链展示（ANP协议调用过程）
            appendThinkingToAgentMessage(messageDiv, data.content);
            break;
            
        case 'video_list':
            // 视频列表
            appendVideoList(messageDiv, data.data);
            break;
            
        case 'progress':
            updateInlineProgress(messageDiv, data.progress, data.message);
            break;
            
        case 'notes_complete':
            appendNotesResult(messageDiv, data.data);
            // 清空当前生成任务ID（任务已完成）
            currentGenerationId = null;
            break;
            
        case 'generate_notes_command':
            // AI触发的笔记生成指令
            console.log('收到AI笔记生成指令:', data.data);
            const { video_index, video_url, video_title } = data.data;
            // 自动触发笔记生成（绕过isProcessing检查）
            triggerNotesGeneration(video_url, video_title, video_index);
            break;
            
        case 'cancelled':
            appendTextToAgentMessage(messageDiv, `⚠️ ${data.content}`, 'error');
            break;
            
        case 'error':
            appendTextToAgentMessage(messageDiv, `❌ 错误: ${data.content}`, 'error');
            break;
            
        default:
            console.warn('未知消息类型:', data.type);
    }
    
    // 滚动到底部
    scrollAgentToBottom();
}

/**
 * 创建Agent消息容器
 */
function createAgentMessageDiv() {
    const container = document.getElementById('agentMessagesContainer');
    
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message message-ai';
    
    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.innerHTML = '<img src="/static/product-logo.png" alt="ViNote" style="width: 100%; height: 100%; object-fit: contain; border-radius: 50%;">';
    
    const content = document.createElement('div');
    content.className = 'message-content';
    
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    
    content.appendChild(bubble);
    messageDiv.appendChild(avatar);
    messageDiv.appendChild(content);
    container.appendChild(messageDiv);
    
    return messageDiv;
}

/**
 * 向Agent消息添加文本
 */
function appendTextToAgentMessage(messageDiv, text, type = 'normal') {
    const bubble = messageDiv.querySelector('.message-bubble');
    
    // 查找或创建文本容器
    let textContainer = bubble.querySelector('.message-text-container');
    if (!textContainer) {
        textContainer = document.createElement('div');
        textContainer.className = type === 'error' ? 'message-error' : 'message-text-container';
        bubble.appendChild(textContainer);
    }
    
    // 累积文本内容
    if (!textContainer.dataset.fullText) {
        textContainer.dataset.fullText = '';
    }
    textContainer.dataset.fullText += text;
    
    // 渲染累积的文本
    if (typeof marked !== 'undefined') {
        textContainer.innerHTML = marked.parse(textContainer.dataset.fullText);
    } else {
        textContainer.textContent = textContainer.dataset.fullText;
    }
}

/**
 * 向Agent消息添加思维链内容（ANP协议调用过程）
 */
function appendThinkingToAgentMessage(messageDiv, content) {
    const bubble = messageDiv.querySelector('.message-bubble');
    
    // 查找或创建思维链容器（始终插入在最前面）
    let thinkingWrapper = bubble.querySelector('.thinking-wrapper');
    if (!thinkingWrapper) {
        thinkingWrapper = document.createElement('div');
        thinkingWrapper.className = 'thinking-wrapper';
        
        // 创建折叠按钮（不显示"思维链"文字）
        const thinkingHeader = document.createElement('div');
        thinkingHeader.className = 'thinking-header';
        thinkingHeader.innerHTML = `
            <button class="thinking-toggle" onclick="toggleThinking(this)" title="折叠/展开">
                <i class="fas fa-chevron-up"></i>
            </button>
        `;
        
        // 创建内容容器
        const thinkingContainer = document.createElement('div');
        thinkingContainer.className = 'thinking-container';
        
        thinkingWrapper.appendChild(thinkingHeader);
        thinkingWrapper.appendChild(thinkingContainer);
        
        // 插入到bubble的最前面
        bubble.insertBefore(thinkingWrapper, bubble.firstChild);
    }
    
    // 添加思维步骤到容器
    const thinkingContainer = thinkingWrapper.querySelector('.thinking-container');
    const thinkingStep = document.createElement('div');
    thinkingStep.className = 'thinking-step';
    
    // 使用 marked 渲染 Markdown 内容
    if (typeof marked !== 'undefined') {
        thinkingStep.innerHTML = marked.parse(content);
    } else {
        thinkingStep.textContent = content;
    }
    
    thinkingContainer.appendChild(thinkingStep);
}

/**
 * 折叠/展开思维链
 */
function toggleThinking(button) {
    const wrapper = button.closest('.thinking-wrapper');
    const container = wrapper.querySelector('.thinking-container');
    const icon = button.querySelector('i');
    
    if (container.style.display === 'none') {
        container.style.display = 'block';
        icon.className = 'fas fa-chevron-up';
        button.title = '折叠';
    } else {
        container.style.display = 'none';
        icon.className = 'fas fa-chevron-down';
        button.title = '展开';
    }
}

/**
 * 添加用户消息
 */
function appendUserMessage(text) {
    const container = document.getElementById('agentMessagesContainer');
    
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message message-user';
    messageDiv.innerHTML = `
        <div class="message-avatar" style="background: linear-gradient(135deg, rgba(76, 140, 245, 0.2) 0%, rgba(90, 156, 247, 0.2) 100%); border: 1px solid rgba(76, 140, 245, 0.3);">
            <i class="fas fa-user" style="color: var(--accent-blue);"></i>
        </div>
        <div class="message-content">
            <div class="message-bubble">${escapeHtml(text)}</div>
        </div>
    `;
    
    container.appendChild(messageDiv);
    scrollAgentToBottom();
}

/**
 * 渲染视频列表（按平台分类，横向滑动）
 */
function appendVideoList(messageDiv, data) {
    const bubble = messageDiv.querySelector('.message-bubble');
    
    // 按平台分类视频
    if (data.videos && data.videos.length > 0) {
        console.log('开始渲染视频列表，总数:', data.videos.length);
        const videosByPlatform = {};
        
        data.videos.forEach((video, index) => {
            const platform = video.platform || 'unknown';
            if (!videosByPlatform[platform]) {
                videosByPlatform[platform] = [];
            }
            videosByPlatform[platform].push({...video, globalIndex: index});
            
            // 保存到结果列表
            currentSearchResults[index] = video;
        });
        
        console.log('按平台分类结果:', Object.keys(videosByPlatform).map(p => `${p}: ${videosByPlatform[p].length}个`));
        
        // 平台显示名称映射
        const platformNames = {
            'bilibili': '📺 哔哩哔哩 (Bilibili)',
            'youtube': '▶️ YouTube',
            'unknown': '🎬 其他平台'
        };
        
        // 为每个平台创建一个横向滑动区域
        Object.keys(videosByPlatform).forEach(platform => {
            const platformVideos = videosByPlatform[platform];
            
            // 平台标题
            const platformHeader = document.createElement('div');
            platformHeader.className = 'platform-header';
            platformHeader.innerHTML = `
                <h4>${platformNames[platform] || platform}</h4>
                <span class="platform-count">${platformVideos.length} 个视频</span>
            `;
            bubble.appendChild(platformHeader);
            
            // 创建横向滑动容器
            const scrollContainer = document.createElement('div');
            scrollContainer.className = 'videos-scroll-container';
            
            const scrollWrapper = document.createElement('div');
            scrollWrapper.className = 'videos-scroll-wrapper';
            
            // 添加视频卡片
            platformVideos.forEach((video, idx) => {
                console.log(`渲染第 ${idx+1} 个视频卡片:`, {
                    title: video.title,
                    cover: video.cover,
                    thumbnail: video.thumbnail,
                    duration: video.duration,
                    author: video.author
                });
                
                const card = document.createElement('div');
                card.className = 'video-card-horizontal';
                card.setAttribute('data-index', video.globalIndex);
                
                // 🔥 先计算好所有需要的值
                const videoUrl = (video.url || '').replace(/'/g, "\\'");
                const videoTitle = (video.title || '未命名视频').replace(/'/g, "\\'");
                
                // 处理图片URL - B站图片需要通过代理
                let thumbnailUrl = video.cover || video.thumbnail || '/static/product-logo.png';
                if (thumbnailUrl !== '/static/product-logo.png' && (thumbnailUrl.includes('bilibili.com') || thumbnailUrl.includes('hdslb.com'))) {
                    // B站图片通过代理加载
                    thumbnailUrl = `/api/proxy-image?url=${encodeURIComponent(thumbnailUrl)}`;
                }
                
                const titleText = escapeHtml(video.title || '未命名视频');
                const authorText = escapeHtml(video.author || '未知作者');
                
                // 🔥 关键：先调用 formatDuration 得到结果，再放入模板
                const durationText = video.duration || '0:00';
                console.log(`视频#${idx+1}: 标题=${video.title}, 封面=${thumbnailUrl}, 时长=${durationText}`);
                
                card.innerHTML = `
                    <div class="video-thumbnail-wrapper">
                        <img src="${thumbnailUrl}" 
                             class="video-thumbnail" 
                             alt="${titleText}"
                             loading="lazy"
                             crossorigin="anonymous"
                             onerror="console.error('图片加载失败:', this.src); this.src='/static/product-logo.png';">
                        <div class="video-duration">${durationText}</div>
                    </div>
                    <div class="video-info-horizontal">
                        <div class="video-title-horizontal">${titleText}</div>
                        <div class="video-author">${authorText}</div>
                        <button class="btn-generate-notes" onclick="selectVideoForNotes('${videoUrl}', '${videoTitle}', ${video.globalIndex})">
                            <i class="fas fa-file-alt"></i> 生成笔记
                        </button>
                    </div>
                `;
                
                scrollWrapper.appendChild(card);
            });
            
            scrollContainer.appendChild(scrollWrapper);
            bubble.appendChild(scrollContainer);
        });
    }
}

/**
 * 渲染视频卡片（旧版，保留兼容）
 */
function appendVideoCard(container, videoData, index) {
    const bubble = container.querySelector('.message-bubble');
    
    const card = document.createElement('div');
    card.className = 'video-card';
    card.setAttribute('data-index', index);
    card.innerHTML = `
        <img src="${videoData.thumbnail || '/static/product-logo.png'}" 
             class="video-thumbnail" 
             alt="${escapeHtml(videoData.title)}"
             onerror="this.src='/static/product-logo.png'">
        <div class="video-info-compact">
            <div class="video-card-title">${escapeHtml(videoData.title)}</div>
            <div class="video-meta-compact">
                <span><i class="fas fa-play-circle"></i> ${escapeHtml(videoData.platform || 'Unknown')}</span>
                <span><i class="fas fa-clock"></i> ${escapeHtml(videoData.duration || 'N/A')}</span>
            </div>
            <div class="video-card-actions">
                <button class="btn-select-video" onclick="selectVideo('${escapeHtml(videoData.url)}', '${escapeHtml(videoData.title)}', ${index})">
                    <i class="fas fa-check"></i> 选择这个视频
                </button>
            </div>
        </div>
    `;
    
    bubble.appendChild(card);
    
    // 保存到结果列表
    if (!currentSearchResults[index]) {
        currentSearchResults[index] = videoData;
    }
}

// 存储当前生成任务ID（用于取消）
let currentGenerationId = null;

/**
 * AI触发的笔记生成（绕过isProcessing检查）
 */
async function triggerNotesGeneration(url, title, index) {
    console.log('AI触发笔记生成:', { url, title, index });
    
    // 找到对应的按钮并更新UI
    const allButtons = document.querySelectorAll('.btn-generate-notes');
    let clickedButton = null;
    let buttonContainer = null;
    
    allButtons.forEach((btn) => {
        const card = btn.closest('.video-card-horizontal');
        if (card && parseInt(card.getAttribute('data-index')) === index) {
            clickedButton = btn;
            buttonContainer = btn.parentElement;
            
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 生成中...';
            btn.style.opacity = '0.7';
        }
    });
    
    // 高亮选中的卡片
    const cards = document.querySelectorAll('.video-card-horizontal');
    cards.forEach((card) => {
        if (parseInt(card.getAttribute('data-index')) === index) {
            card.style.borderColor = 'var(--accent-green)';
            card.style.backgroundColor = 'rgba(34, 197, 94, 0.05)';
        }
    });
    
    // 创建进度消息
    const progressMessageDiv = createAgentMessageDiv();
    
    try {
        await streamNotesGeneration(url, progressMessageDiv);
        
        // 生成成功后，更新按钮状态为"已生成"
        if (clickedButton) {
            clickedButton.disabled = false;
            clickedButton.innerHTML = '<i class="fas fa-check-circle"></i> 已生成';
            clickedButton.style.opacity = '1';
            clickedButton.style.background = 'linear-gradient(135deg, rgba(34, 197, 94, 0.15) 0%, rgba(52, 211, 153, 0.2) 100%)';
            clickedButton.style.borderColor = 'var(--accent-green)';
            clickedButton.style.color = 'var(--accent-green)';
        }
    } catch (error) {
        console.error('生成笔记失败:', error);
        appendErrorMessage('生成笔记失败: ' + error.message);
        
        // 失败后恢复按钮
        if (clickedButton) {
            clickedButton.disabled = false;
            clickedButton.innerHTML = '<i class="fas fa-file-alt"></i> 生成笔记';
            clickedButton.style.opacity = '1';
        }
    }
}

/**
 * 用户选择视频生成笔记
 */
async function selectVideoForNotes(url, title, index) {
    console.log('用户选择视频生成笔记:', { url, title, index });
    
    if (isProcessing) {
        showMessage('请等待当前任务完成', 'info');
        return;
    }
    
    // 找到被点击的按钮，更新为"生成中..."
    const allButtons = document.querySelectorAll('.btn-generate-notes');
    let clickedButton = null;
    
    allButtons.forEach((btn, i) => {
        const card = btn.closest('.video-card-horizontal');
        if (card && parseInt(card.getAttribute('data-index')) === index) {
            clickedButton = btn;
            
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 生成中...';
            btn.style.opacity = '0.7';
        }
    });
    
    // 高亮选中的卡片
    const cards = document.querySelectorAll('.video-card-horizontal');
    cards.forEach((card, i) => {
        if (parseInt(card.getAttribute('data-index')) === index) {
            card.style.borderColor = 'var(--accent-green)';
            card.style.backgroundColor = 'rgba(34, 197, 94, 0.05)';
        }
    });
    
    // 显示用户选择
    appendUserMessage(`✅ 开始为《${title}》生成笔记`);
    
    // 标记处理中
    isProcessing = true;
    
    // 创建进度消息
    const progressMessageDiv = createAgentMessageDiv();
    
    try {
        await streamNotesGeneration(url, progressMessageDiv);
        
        // 生成成功后，更新按钮状态为"已生成"
        if (clickedButton) {
            clickedButton.disabled = false;
            clickedButton.innerHTML = '<i class="fas fa-check-circle"></i> 已生成';
            clickedButton.style.opacity = '1';
            clickedButton.style.background = 'linear-gradient(135deg, rgba(34, 197, 94, 0.15) 0%, rgba(52, 211, 153, 0.2) 100%)';
            clickedButton.style.borderColor = 'var(--accent-green)';
            clickedButton.style.color = 'var(--accent-green)';
        }
    } catch (error) {
        console.error('生成笔记失败:', error);
        appendErrorMessage('生成笔记失败: ' + error.message);
        
        // 失败后恢复按钮
        if (clickedButton) {
            clickedButton.disabled = false;
            clickedButton.innerHTML = '<i class="fas fa-file-alt"></i> 生成笔记';
            clickedButton.style.opacity = '1';
        }
    } finally {
        isProcessing = false;
    }
}

/**
 * 流式生成笔记
 */
async function streamNotesGeneration(videoUrl, messageDiv) {
    const response = await fetch('/api/search-agent-generate-notes', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'text/event-stream'
        },
        body: JSON.stringify({
            video_url: videoUrl,
            summary_language: 'zh'
        })
    });
    
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    
    try {
        while (true) {
            const { done, value } = await reader.read();
            
            if (done) {
                console.log('笔记生成完成');
                break;
            }
            
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';
            
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        handleAgentMessage(data, messageDiv);
                    } catch (e) {
                        console.error('解析笔记生成消息失败:', e, line);
                    }
                }
            }
        }
    } finally {
        // 完成
    }
}

/**
 * 用户选择视频（旧版，保留兼容）
 */
async function selectVideo(url, title, index) {
    console.log('用户选择视频:', { url, title, index });
    
    // 禁用所有选择按钮
    const buttons = document.querySelectorAll('.btn-select-video');
    buttons.forEach(btn => {
        btn.disabled = true;
        btn.style.opacity = '0.5';
    });
    
    // 高亮选中的卡片
    const cards = document.querySelectorAll('.video-card');
    cards.forEach((card, i) => {
        if (i === index) {
            card.style.borderColor = 'var(--accent-green)';
            card.style.backgroundColor = 'rgba(34, 197, 94, 0.05)';
        }
    });
    
    // 构造消息
    const message = `我要处理这个视频: ${title}`;
    
    // 添加到历史(附带视频URL)
    conversationHistory.push({
        role: 'user',
        content: message,
        video_url: url,
        video_title: title
    });
    
    // 显示用户选择
    appendUserMessage(`✅ 已选择: ${title}`);
    
    // 发送处理请求
    isProcessing = true;
    showAgentTyping();
    
    try {
        await streamAgentResponse(message);
    } catch (error) {
        console.error('处理视频失败:', error);
        hideAgentTyping();
        appendErrorMessage('处理视频失败: ' + error.message);
    } finally {
        isProcessing = false;
    }
}

/**
 * 更新内联进度条
 */
function updateInlineProgress(container, progress, message) {
    const bubble = container.querySelector('.message-bubble');
    let progressDiv = bubble.querySelector('.inline-progress');
    
    if (!progressDiv) {
        progressDiv = document.createElement('div');
        progressDiv.className = 'inline-progress';
        progressDiv.innerHTML = `
            <div class="inline-progress-text"></div>
            <div class="inline-progress-bar">
                <div class="inline-progress-fill"></div>
            </div>
            <div class="inline-progress-percent">0%</div>
        `;
        bubble.appendChild(progressDiv);
        
        // 在进度条后面添加取消按钮（与生成笔记按钮样式一致）
        let cancelBtn = bubble.querySelector('.btn-cancel-inline');
        if (!cancelBtn) {
            cancelBtn = document.createElement('button');
            cancelBtn.className = 'btn-generate-notes btn-cancel-inline';
            cancelBtn.innerHTML = '<i class="fas fa-times"></i> 取消';
            cancelBtn.onclick = cancelInlineGeneration;
            cancelBtn.style.marginTop = '12px';
            cancelBtn.style.background = 'linear-gradient(135deg, rgba(239, 68, 68, 0.1) 0%, rgba(220, 38, 38, 0.15) 100%)';
            cancelBtn.style.borderColor = 'rgba(239, 68, 68, 0.3)';
            cancelBtn.style.color = '#ef4444';
            bubble.appendChild(cancelBtn);
        }
    }
    
    const textEl = progressDiv.querySelector('.inline-progress-text');
    const fillEl = progressDiv.querySelector('.inline-progress-fill');
    const percentEl = progressDiv.querySelector('.inline-progress-percent');
    
    textEl.textContent = message;
    fillEl.style.width = `${progress}%`;
    percentEl.textContent = `${progress}%`;
}

/**
 * 取消内联生成任务
 */
async function cancelInlineGeneration() {
    if (!currentGenerationId) {
        showMessage('没有正在进行的生成任务', 'info');
        return;
    }
    
    console.log('取消内联生成任务:', currentGenerationId);
    
    try {
        const response = await fetch(`/api/search-agent-cancel-generation/${currentGenerationId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            console.log('生成任务已取消');
            showMessage('已取消生成', 'info');
        } else {
            console.warn('取消任务失败:', await response.text());
            showMessage('取消失败', 'error');
        }
    } catch (error) {
        console.error('调用取消API失败:', error);
        showMessage('取消失败', 'error');
    }
}

/**
 * 渲染笔记结果
 */
function appendNotesResult(container, notesData) {
    const bubble = container.querySelector('.message-bubble');
    
    // 移除进度条和取消按钮
    const progressDiv = bubble.querySelector('.inline-progress');
    if (progressDiv) {
        progressDiv.remove();
    }
    const cancelBtn = bubble.querySelector('.btn-cancel-inline');
    if (cancelBtn) {
        cancelBtn.remove();
    }
    
    console.log('渲染笔记结果:', notesData);
    
    // 获取文件名，支持多种可能的字段名
    const transcriptFile = notesData.files?.transcript_filename || notesData.files?.transcript || '';
    const summaryFile = notesData.files?.summary_filename || notesData.files?.summary || '';
    const rawFile = notesData.files?.raw_transcript_filename || notesData.files?.raw || '';
    
    console.log('文件名:', { transcriptFile, summaryFile, rawFile });
    
    const resultCard = document.createElement('div');
    resultCard.className = 'notes-result-card';
    resultCard.innerHTML = `
        <h3 style="margin-bottom: 12px;">
            <i class="fas fa-check-circle" style="color: var(--accent-green);"></i> 
            ${escapeHtml(notesData.video_title || notesData.title || '笔记已生成')}
        </h3>
        <div class="notes-preview">${escapeHtml(notesData.summary || notesData.transcript || '笔记内容')}</div>
        <div class="download-buttons-inline">
            <button class="btn btn-sm" onclick="downloadAgentFile('${transcriptFile}')" ${!transcriptFile ? 'disabled' : ''}>
                <i class="fas fa-download"></i> 完整笔记
            </button>
            <button class="btn btn-sm" onclick="downloadAgentFile('${summaryFile}')" ${!summaryFile ? 'disabled' : ''}>
                <i class="fas fa-download"></i> 摘要
            </button>
            <button class="btn btn-sm" onclick="downloadAgentFile('${rawFile}')" ${!rawFile ? 'disabled' : ''}>
                <i class="fas fa-download"></i> 原文
            </button>
        </div>
    `;
    
    bubble.appendChild(resultCard);
}

/**
 * 下载文件
 */
function downloadAgentFile(filename) {
    if (!filename) {
        showMessage('文件名无效', 'error');
        return;
    }
    
    const link = document.createElement('a');
    link.href = `/api/download/${filename}`;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    showMessage('开始下载...', 'success');
}

/**
 * 添加错误消息
 */
function appendErrorMessage(message) {
    const container = document.getElementById('agentMessagesContainer');
    
    const errorDiv = document.createElement('div');
    errorDiv.className = 'message message-ai';
    errorDiv.innerHTML = `
        <div class="message-avatar">
            <i class="fas fa-exclamation-triangle"></i>
        </div>
        <div class="message-content">
            <div class="message-bubble message-error">
                ${escapeHtml(message)}
            </div>
        </div>
    `;
    
    container.appendChild(errorDiv);
    scrollAgentToBottom();
}

/**
 * 显示输入中状态
 */
function showAgentTyping() {
    const container = document.getElementById('agentMessagesContainer');
    
    // 移除旧的输入提示
    const oldTyping = document.getElementById('agentTyping');
    if (oldTyping) oldTyping.remove();
    
    const typing = document.createElement('div');
    typing.id = 'agentTyping';
    typing.className = 'message message-ai';
    typing.innerHTML = `
        <div class="message-avatar">
            <img src="/static/product-logo.png" alt="ViNote" style="width: 100%; height: 100%; object-fit: contain; border-radius: 50%;">
        </div>
        <div class="message-content">
            <div class="message-bubble">
                <div class="typing-indicator">
                    <span class="typing-dot"></span>
                    <span class="typing-dot"></span>
                    <span class="typing-dot"></span>
                </div>
            </div>
        </div>
    `;
    
    container.appendChild(typing);
    scrollAgentToBottom();
}

/**
 * 隐藏输入中状态
 */
function hideAgentTyping() {
    const typing = document.getElementById('agentTyping');
    if (typing) {
        typing.remove();
    }
}

/**
 * 滚动到底部
 */
function scrollAgentToBottom() {
    const container = document.getElementById('agentMessagesContainer');
    if (container) {
        setTimeout(() => {
            container.scrollTop = container.scrollHeight;
        }, 100);
    }
}

/**
 * 清空对话
 */
async function clearAgentConversation() {
    if (!confirm('确定要清空当前对话吗?')) return;
    
    try {
        // 通知后端清空会话
        await fetch('/api/search-agent-clear-session', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: agentSessionId })
        });
        
        // 重新生成会话ID（开启新对话）
        agentSessionId = generateSessionId();
        currentSearchResults = [];
        
        // 清空UI
        const container = document.getElementById('agentMessagesContainer');
        container.innerHTML = '';
        
        showAgentWelcomeMessage();
        showMessage('对话已清空，开启新会话', 'success');
    } catch (error) {
        console.error('清空对话失败:', error);
        showMessage('清空对话失败', 'error');
    }
}

/**
 * 生成会话ID
 */
function generateSessionId() {
    return 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
}

/**
 * HTML转义
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}


/**
 * 输入框回车发送
 */
document.addEventListener('DOMContentLoaded', function() {
    const agentInput = document.getElementById('agentInput');
    if (agentInput) {
        agentInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendAgentMessage();
            }
        });
    }
});
