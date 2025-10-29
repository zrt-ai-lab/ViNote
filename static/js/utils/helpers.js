/**
 * 工具函数和全局函数
 * 包含页面路由、QA功能、全局函数导出等
 */

// 页面路由映射
const workspacePages = {
    'notes': 'workspacePage',
    'qa': 'qaWorkspace',
    'search-agent': 'searchAgentWorkspace',
    'publish': 'publishWorkspace',
    'subtitle': 'subtitleWorkspace',
    'flashcard': 'flashcardWorkspace',
    'mindmap': 'mindmapWorkspace'
};

// 格式化时长（支持秒数或已格式化字符串）
function formatDuration(duration) {
    // 如果已经是字符串格式（如 "176:26"），直接返回
    if (typeof duration === 'string' && duration.includes(':')) {
        return duration;
    }
    
    // 如果是数字，转换为格式化字符串
    const seconds = typeof duration === 'number' ? duration : parseFloat(duration);
    if (!seconds || seconds === 0 || isNaN(seconds)) return '0:00';
    
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    
    if (hours > 0) {
        return `${hours}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    } else {
        return `${minutes}:${String(secs).padStart(2, '0')}`;
    }
}

// QA状态管理

let qaState = {
    videoInfo: null,
    transcript: null,
    taskId: null,
    eventSource: null,
    conversationHistory: []
};

// 页面路由函数
function enterWorkspace(pageType = 'notes') {
    // 🔥 清除所有缓存和状态
    clearPageStateCache();
    clearAllWorkspaceStates();
    const targetPageId = workspacePages[pageType];
    const targetPage = document.getElementById(targetPageId);
    if (!targetPage) {
        alert(`${pageType} 功能即将上线，敬请期待！`);
        return;
    }
    targetPage.style.display = 'grid';
    targetPage.style.animation = 'fadeIn 0.6s ease-out';
    document.getElementById('landingPage').style.display = 'none';
    const logo = document.querySelector('.landing-logo');
    if (logo) logo.style.display = 'none';
    Object.values(workspacePages).forEach(pageId => {
        if (pageId !== targetPageId) {
            const page = document.getElementById(pageId);
            if (page) page.style.display = 'none';
        }
    });
    
    // 清理笔记页面
    if (app) {
        if (app.videoUrl) app.videoUrl.value = '';
        if (app.videoPreview) {
            app.videoPreview.style.display = 'none';
            app.videoPreview.classList.remove('show');
            if (app.videoPlayer) app.videoPlayer.innerHTML = '';
        }
        if (app.progressSection) app.progressSection.style.display = 'none';
        if (app.downloadSection) app.downloadSection.style.display = 'none';
        if (app.resultsSection) app.resultsSection.style.display = 'none';
        app.currentVideoInfo = null;
        app.currentTaskId = null;
        app.currentDownloadId = null;
        app.disableActionButtons();
        
        // 显示空状态
        const emptyState = document.getElementById('emptyState');
        if (emptyState) emptyState.style.display = 'flex';
    }
    
    // 清理问答页面
    if (pageType === 'qa') {
        // 重置QA状态
        qaState = { videoInfo: null, transcript: null, taskId: null, eventSource: null, conversationHistory: [] };
        
        // 清空输入框
        const qaVideoUrl = document.getElementById('qaVideoUrl');
        if (qaVideoUrl) qaVideoUrl.value = '';
        
        // 显示空状态，隐藏预览
        const qaEmptyState = document.getElementById('qaEmptyState');
        const qaVideoPreview = document.getElementById('qaVideoPreview');
        if (qaEmptyState) {
            qaEmptyState.style.display = 'flex';
            // 🔥 重置为初始空状态内容
            qaEmptyState.innerHTML = `
                <i class="fas fa-video"></i>
                <p>暂无视频</p>
                <span class="hint">请输入视频链接开始</span>
            `;
        }
        if (qaVideoPreview) {
            qaVideoPreview.style.display = 'none';
            qaVideoPreview.classList.remove('show');
        }
        
        // 清空对话记录
        const messagesContainer = document.getElementById('messagesContainer');
        const qaWelcomeMessage = document.getElementById('qaWelcomeMessage');
        if (messagesContainer) {
            messagesContainer.innerHTML = '';
            messagesContainer.style.display = 'none';
        }
        if (qaWelcomeMessage) {
            qaWelcomeMessage.style.display = 'block';
        }
        
        // 禁用输入和按钮
        const questionInput = document.getElementById('questionInput');
        const askBtn = document.getElementById('askBtn');
        if (questionInput) {
            questionInput.disabled = true;
            questionInput.value = '';
        }
        if (askBtn) askBtn.disabled = true;
        
        // 重置预处理按钮
        const qaPreprocessBtn = document.getElementById('qaPreprocessBtn');
        const qaPreprocessBtnProgress = document.getElementById('qaPreprocessBtnProgress');
        const qaPreprocessPercent = document.getElementById('qaPreprocessPercent');
        if (qaPreprocessBtn) {
            qaPreprocessBtn.disabled = true;
            qaPreprocessBtn.classList.remove('processing');
            const btnContent = qaPreprocessBtn.querySelector('.btn-content');
            if (btnContent) {
                btnContent.innerHTML = `
                    <i class="fas fa-cog"></i>
                    <span>开始预处理</span>
                    <span id="qaPreprocessPercent" style="margin-left: 8px; font-size: 0.9em; opacity: 0; transition: opacity 0.3s;">0%</span>
                `;
            }
        }
        if (qaPreprocessBtnProgress) {
            qaPreprocessBtnProgress.style.width = '0%';
        }
    }
}

function backToLanding() {
    clearPageStateCache();
    Object.values(workspacePages).forEach(pageId => {
        const page = document.getElementById(pageId);
        if (page) page.style.display = 'none';
    });
    document.getElementById('landingPage').style.display = 'flex';
    const logo = document.querySelector('.landing-logo');
    if (logo) logo.style.display = 'block';
    window.scrollTo(0, 0);
}

function toggleContactCard() {
    const card = document.getElementById('contactCard');
    if (card) card.classList.toggle('show');
}

// 更新QA预览按钮状态
function updateQAPreviewButtonState(state) {
    const previewBtn = document.getElementById('qaPreviewBtn');
    if (!previewBtn) return;
    
    const btnContent = previewBtn.querySelector('.btn-content');
    if (!btnContent) return;
    
    if (state === 'loading') {
        // 加载中状态 - 禁用并显示加载动画
        previewBtn.disabled = true;
        previewBtn.style.opacity = '0.7';
        previewBtn.style.cursor = 'not-allowed';
        btnContent.innerHTML = `
            <i class="fas fa-spinner fa-spin"></i>
            <span>预览中...</span>
        `;
    } else {
        // 空闲状态
        previewBtn.disabled = false;
        previewBtn.style.opacity = '1';
        previewBtn.style.cursor = 'pointer';
        btnContent.innerHTML = `
            <i class="fas fa-eye"></i>
            <span>预览</span>
        `;
    }
}

// 全局函数导出（供HTML onclick使用）
function toggleLanguage() { if (app) app.toggleLanguage(); }
function previewVideo() { if (app) app.previewVideo(); }
function startTranscription() { if (app) app.startTranscription(); }
function showDownloadModal() { if (app) app.showDownloadModal(); }
function closeDownloadModal() { if (app) app.closeDownloadModal(); }
function selectQuality(quality) { if (app) app.selectQuality(quality); }
function confirmDownload() { if (app) app.confirmDownload(); }
function showTab(tabName) { if (app) app.showTab(tabName); }
function downloadContent(type) { if (app) app.downloadContent(type); }
function cancelTask() { if (app) app.cancelTask(); }
function cancelDownload() { if (app) app.cancelDownload(); }
function handleDownloadClick() { if (app) app.handleDownloadClick(); }

// QA页面专用函数
async function previewVideoForQA() {
    // 如果正在预处理,禁止预览
    if (qaState.taskId) {
        console.log('正在预处理中,禁止预览');
        return;
    }
    
    // 🔥 防止重复点击
    if (window.qaPreviewingInProgress) {
        console.log('正在预览中，忽略重复点击');
        return;
    }
    
    const qaVideoUrl = document.getElementById('qaVideoUrl');
    let url = qaVideoUrl?.value?.trim();
    
    if (!url) {
        alert('请输入视频链接');
        return;
    }
    
    // 智能提取URL（处理分享文本）
    if (app && app.extractUrl) {
        url = app.extractUrl(url);
        if (!url) {
            alert('未能识别有效的视频链接');
            return;
        }
    }
    
    // 🔥 立即设置标志
    window.qaPreviewingInProgress = true;
    console.log('✅ 设置QA预览进行中标志');
    
    try {
        const qaEmptyState = document.getElementById('qaEmptyState');
        const qaVideoPreview = document.getElementById('qaVideoPreview');
        
        // 🔥 第一步：强制显示emptyState并显示loading
        if (qaEmptyState) {
            qaEmptyState.style.display = 'flex';
            qaEmptyState.innerHTML = `
                <div class="loading-spinner"></div>
                <p style="color: var(--text-secondary); margin-top: 20px;">正在获取视频信息...</p>
                <span class="hint">请稍候片刻</span>
            `;
        }
        
        // 🔥 第二步：隐藏预览内容
        if (qaVideoPreview) {
            qaVideoPreview.style.display = 'none';
            qaVideoPreview.classList.remove('show');
        }
        
        // 更新预览按钮为加载中状态
        updateQAPreviewButtonState('loading');
        
        // 调用后端API获取视频信息
        const response = await fetch(`/api/preview-video?url=${encodeURIComponent(url)}`);
        const result = await response.json();
        
        console.log('预览API响应:', result);
        
        if (!response.ok) {
            throw new Error(result.detail || '获取视频信息失败');
        }
        
        // 处理响应数据
        if (result.success && result.data) {
            qaState.videoInfo = result.data;
            
            // 隐藏空状态
            if (qaEmptyState) {
                qaEmptyState.style.display = 'none';
            }
            
            // 显示视频预览
            displayQAVideoPreview(result.data);
            
            // 恢复预览按钮状态
            updateQAPreviewButtonState('idle');
        } else {
            throw new Error('返回数据格式错误');
        }
        
    } catch (error) {
        console.error('预览视频失败:', error);
        
        // 恢复空状态
        const qaEmptyState = document.getElementById('qaEmptyState');
        if (qaEmptyState) {
            qaEmptyState.style.display = 'flex';
            qaEmptyState.innerHTML = `
                <i class="fas fa-video"></i>
                <p>预览失败</p>
                <span class="hint">${error.message}</span>
            `;
        }
        
        const qaVideoPreview = document.getElementById('qaVideoPreview');
        if (qaVideoPreview) {
            qaVideoPreview.style.display = 'none';
        }
        
        // 恢复预览按钮状态
        updateQAPreviewButtonState('idle');
        
        alert(`预览失败: ${error.message}`);
    } finally {
        // 🔥 重置标志，允许下次预览
        window.qaPreviewingInProgress = false;
        console.log('✅ 重置QA预览标志');
    }
}

function displayQAVideoPreview(videoInfo) {
    const qaVideoPreview = document.getElementById('qaVideoPreview');
    
    if (!qaVideoPreview) return;
    
    console.log('开始显示QA视频预览，视频信息:', videoInfo);
    
    // 构建播放器HTML
    let playerHTML = '';
    if (videoInfo.embed_url) {
        console.log('添加嵌入播放器:', videoInfo.embed_url);
        // 🎯 使用16:9宽高比的响应式容器，消除黑边
        playerHTML = `
            <div style="position: relative; width: 100%; padding-bottom: 56.25%; height: 0; overflow: hidden; border-radius: 12px; background: #000;">
                <iframe src="${videoInfo.embed_url}" 
                        frameborder="0" 
                        allowfullscreen
                        style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; border: none;">
                </iframe>
            </div>
        `;
    } else {
        console.log('不支持嵌入播放');
        playerHTML = '<p style="color: var(--text-muted); text-align: center; padding: 40px;">无法加载视频播放器</p>';
    }
    
    // 获取视频信息
    const title = videoInfo.title || '未知标题';
    const description = videoInfo.description || '无描述';
    
    console.log('设置标题:', title);
    console.log('设置描述:', description);
    
    // 🔥 与笔记页面保持一致的元数据项
    const metaItems = [
        { label: '时长', value: videoInfo.duration_string || '未知' },
        { label: '上传者', value: videoInfo.uploader || '未知' },
        { label: '观看次数', value: videoInfo.view_count_string || '0' },
        { label: '上传日期', value: videoInfo.upload_date || '未知' }
    ];
    
    const metaHTML = metaItems.map(item => `
        <div class="meta-item">
            <div class="meta-label">${item.label}</div>
            <div class="meta-value">${item.value}</div>
        </div>
    `).join('');
    
    // 🔥 重新构建完整的预览HTML - 与笔记页面布局一致
    qaVideoPreview.innerHTML = `
        <!-- 预处理按钮（带进度条）- 移到顶部 -->
        <button id="qaPreprocessBtn" class="btn btn-secondary btn-full btn-with-progress" onclick="preprocessVideoForQA()" style="margin-bottom: 20px; position: relative; overflow: hidden;">
            <div class="btn-progress-bg" id="qaPreprocessBtnProgress" style="position: absolute; left: 0; top: 0; height: 100%; width: 0%; background: linear-gradient(90deg, rgba(76, 140, 245, 0.4) 0%, rgba(90, 156, 247, 0.6) 100%); transition: width 0.3s ease; z-index: 0;"></div>
            <span class="btn-content" style="position: relative; z-index: 1; display: flex; align-items: center; justify-content: center; gap: 8px;">
                <i class="fas fa-cog"></i>
                <span>开始预处理</span>
                <span id="qaPreprocessPercent" style="margin-left: 8px; font-size: 0.9em; opacity: 0; transition: opacity 0.3s;">0%</span>
            </span>
        </button>
        
        <h3 class="video-title" id="qaVideoTitle">${title}</h3>
        <div class="video-player" id="qaVideoPlayer">${playerHTML}</div>
        <p class="video-description" id="qaVideoDescription">${description}</p>
        <div class="video-meta" id="qaVideoMeta">${metaHTML}</div>
    `;
    
    // 显示预览区域
    qaVideoPreview.style.display = 'block';
    qaVideoPreview.classList.add('show');
    console.log('QA预览区域已设置为显示');
    
    // 滚动到预览区域
    qaVideoPreview.scrollIntoView({ behavior: 'smooth', block: 'center' });
    
    console.log('✅ QA视频预览已显示');
}

async function preprocessVideoForQA() {
    const preprocessBtn = document.getElementById('qaPreprocessBtn');
    
    // 🔥 如果正在处理中，点击则取消
    if (qaState.taskId && preprocessBtn.classList.contains('processing')) {
        cancelQAPreprocess();
        return;
    }
    
    const url = document.getElementById('qaVideoUrl')?.value?.trim();
    if (!url || !qaState.videoInfo) {
        alert('请先预览视频');
        return;
    }

    try {
        const btnProgress = document.getElementById('qaPreprocessBtnProgress');
        const btnContent = preprocessBtn.querySelector('.btn-content');
        
        // 🔥 禁用预览按钮,防止预处理时点击预览
        const qaPreviewBtn = document.getElementById('qaPreviewBtn');
        if (qaPreviewBtn) {
            qaPreviewBtn.disabled = true;
            qaPreviewBtn.style.opacity = '0.5';
            qaPreviewBtn.style.cursor = 'not-allowed';
        }
        
        // 🔥 更新按钮为处理中状态（显示取消按钮）
        if (preprocessBtn) {
            preprocessBtn.disabled = false; // 保持可点击用于取消
            preprocessBtn.classList.add('processing');
            
            // 更新按钮内容为取消
            if (btnContent) {
                btnContent.innerHTML = `
                    <i class="fas fa-times"></i>
                    <span>取消预处理</span>
                    <span id="qaPreprocessPercent" style="margin-left: 8px; font-size: 0.9em; opacity: 1; transition: opacity 0.3s;">0%</span>
                `;
            }
        }
        
        // 调用轻量级转录API（只转录，不生成摘要）
        const formData = new FormData();
        formData.append('url', url);
        
        const response = await fetch('/api/transcribe-only', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();
        
        if (!response.ok) {
            throw new Error(result.detail || '转录失败');
        }

        qaState.taskId = result.task_id;
        console.log('✅ 启动轻量级转录任务:', qaState.taskId);
        startQAProgressStream();
        
    } catch (error) {
        console.error('转录错误:', error);
        
        // 恢复按钮状态
        const preprocessBtn = document.getElementById('qaPreprocessBtn');
        const btnProgress = document.getElementById('qaPreprocessBtnProgress');
        const btnContent = preprocessBtn?.querySelector('.btn-content');
        
        if (preprocessBtn) {
            preprocessBtn.disabled = false;
            preprocessBtn.classList.remove('processing');
            if (btnProgress) btnProgress.style.width = '0%';
            if (btnContent) {
                btnContent.innerHTML = `
                    <i class="fas fa-cog"></i>
                    <span>开始预处理</span>
                    <span id="qaPreprocessPercent" style="margin-left: 8px; font-size: 0.9em; opacity: 0; transition: opacity 0.3s;">0%</span>
                `;
            }
        }
        
        alert(`转录失败: ${error.message}`);
    }
}

// 取消预处理
async function cancelQAPreprocess() {
    if (!qaState.taskId) {
        return;
    }

    try {
        console.log(`正在取消预处理任务: ${qaState.taskId}`);
        
        const response = await fetch(`/api/task/${qaState.taskId}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            // 停止进度流
            if (qaState.eventSource) {
                qaState.eventSource.close();
                qaState.eventSource = null;
            }
            
            // 恢复按钮状态
            const preprocessBtn = document.getElementById('qaPreprocessBtn');
            const btnProgress = document.getElementById('qaPreprocessBtnProgress');
            const btnContent = preprocessBtn?.querySelector('.btn-content');
            
            if (preprocessBtn) {
                preprocessBtn.disabled = false;
                preprocessBtn.classList.remove('processing');
                if (btnProgress) btnProgress.style.width = '0%';
                if (btnContent) {
                    btnContent.innerHTML = `
                        <i class="fas fa-cog"></i>
                        <span>开始预处理</span>
                        <span id="qaPreprocessPercent" style="margin-left: 8px; font-size: 0.9em; opacity: 0; transition: opacity 0.3s;">0%</span>
                    `;
                }
            }
            
            // 恢复预览按钮
            const qaPreviewBtn = document.getElementById('qaPreviewBtn');
            if (qaPreviewBtn) {
                qaPreviewBtn.disabled = false;
                qaPreviewBtn.style.opacity = '1';
                qaPreviewBtn.style.cursor = 'pointer';
            }
            
            // 清空任务ID
            qaState.taskId = null;
            
            alert('预处理已取消');
        } else {
            throw new Error('取消失败');
        }
    } catch (error) {
        console.error('取消预处理错误:', error);
        alert(`取消预处理失败: ${error.message}`);
    }
}

// 监听预处理进度
function startQAProgressStream() {
    if (qaState.eventSource) {
        qaState.eventSource.close();
    }

    qaState.eventSource = new EventSource(`/api/task-stream/${qaState.taskId}`);
    
    qaState.eventSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            updateQAProgress(data);
        } catch (error) {
            console.error('解析进度数据失败:', error);
        }
    };

    qaState.eventSource.onerror = (error) => {
        console.error('SSE连接错误:', error);
    };
}

// 更新问答页面的进度
function updateQAProgress(data) {
    if (data.type === 'heartbeat') return;

    const progress = data.progress || 0;
    
    // 更新按钮内的进度条
    const btnProgress = document.getElementById('qaPreprocessBtnProgress');
    if (btnProgress) {
        btnProgress.style.width = `${progress}%`;
    }
    
    // 更新百分比显示
    const percentElem = document.getElementById('qaPreprocessPercent');
    if (percentElem) {
        percentElem.style.opacity = '1';
        percentElem.textContent = `${Math.round(progress)}%`;
    }

    if (data.status === 'completed') {
        onQAPreprocessCompleted(data);
    } else if (data.status === 'error') {
        onQAPreprocessError(data);
    }
}

// 预处理完成 - 全局函数,供URL和本地路径模式共用
window.onQAPreprocessCompleted = function(data) {
    if (qaState.eventSource) {
        qaState.eventSource.close();
        qaState.eventSource = null;
    }

    // 保存转录文本
    qaState.transcript = data.transcript || '';
    
    // 更新按钮为完成状态
    const preprocessBtn = document.getElementById('qaPreprocessBtn');
    const btnProgress = document.getElementById('qaPreprocessBtnProgress');
    const btnContent = preprocessBtn?.querySelector('.btn-content');
    const percentElem = document.getElementById('qaPreprocessPercent');
    
    if (btnProgress) btnProgress.style.width = '100%';
    
    // 隐藏百分比显示
    if (percentElem) percentElem.style.display = 'none';
    
    // 禁用按钮，移除处理中类，清空任务ID
    if (preprocessBtn) {
        preprocessBtn.disabled = true;
        preprocessBtn.classList.remove('processing');
        preprocessBtn.style.cursor = 'not-allowed';
    }
    
    // 清空任务ID
    qaState.taskId = null;
    
    // 居中显示完成状态
    if (btnContent) {
        btnContent.style.justifyContent = 'center';
        btnContent.innerHTML = `
            <i class="fas fa-check"></i>
            <span>预处理完成</span>
        `;
    }
    
    // 2秒后隐藏按钮
    setTimeout(() => {
        const preview = document.getElementById('qaVideoPreview');
        if (preview) preview.style.display = 'none';
    }, 2000);
    
    // 隐藏欢迎消息，显示对话容器
    const welcomeMsg = document.getElementById('qaWelcomeMessage');
    const messagesContainer = document.getElementById('messagesContainer');
    
    if (welcomeMsg) welcomeMsg.style.display = 'none';
    if (messagesContainer) {
        messagesContainer.style.display = 'flex';
        messagesContainer.style.flexDirection = 'column';
        messagesContainer.style.gap = '20px';
    }
    
    // 启用输入框和按钮
    const questionInput = document.getElementById('questionInput');
    const askBtn = document.getElementById('askBtn');
    
    if (questionInput) questionInput.disabled = false;
    if (askBtn) askBtn.disabled = false;
    
    // 🔥 添加系统欢迎消息
    addQAMessage('ai', `✨ 视频预处理完成！我已经了解了这个视频的内容，现在可以回答您的任何问题了。您可以：

• 询问视频的主要内容
• 提取关键要点和知识点
• 请我解释某个概念
• 询问视频中的实例和案例

请随时向我提问！`);
}

// 预处理错误
function onQAPreprocessError(data) {
    if (qaState.eventSource) {
        qaState.eventSource.close();
        qaState.eventSource = null;
    }

    // 🔥 恢复按钮状态
    const preprocessBtn = document.getElementById('qaPreprocessBtn');
    const btnProgress = document.getElementById('qaPreprocessBtnProgress');
    const btnContent = preprocessBtn?.querySelector('.btn-content');
    const percentElem = document.getElementById('qaPreprocessPercent');
    
    if (preprocessBtn) {
        preprocessBtn.disabled = false;
        preprocessBtn.classList.remove('processing');
    }
    if (btnProgress) btnProgress.style.width = '0%';
    if (percentElem) {
        percentElem.style.opacity = '0';
        percentElem.textContent = '0%';
    }
    if (btnContent) {
        btnContent.innerHTML = `
            <i class="fas fa-cog"></i>
            <span>开始预处理</span>
            <span id="qaPreprocessPercent" style="margin-left: 8px; font-size: 0.9em; opacity: 0; transition: opacity 0.3s;">0%</span>
        `;
    }
    
    // 🔥 恢复预览按钮
    const qaPreviewBtn = document.getElementById('qaPreviewBtn');
    if (qaPreviewBtn) {
        qaPreviewBtn.disabled = false;
        qaPreviewBtn.style.opacity = '1';
        qaPreviewBtn.style.cursor = 'pointer';
    }
    
    // 🔥 清空任务ID，防止重复弹窗
    qaState.taskId = null;
    
    // 只弹一次错误提示
    alert(`预处理失败: ${data.error || '未知错误'}`);
}

async function askQuestion() {
    const questionInput = document.getElementById('questionInput');
    const question = questionInput?.value?.trim();
    
    if (!question) {
        alert('请输入问题');
        return;
    }
    
    if (!qaState.transcript) {
        alert('请先完成视频预处理');
        return;
    }
    
    try {
        const messagesContainer = document.getElementById('messagesContainer');
        const qaWelcomeMessage = document.getElementById('qaWelcomeMessage');
        
        // 显示消息容器
        if (messagesContainer) {
            messagesContainer.style.display = 'block';
        }
        if (qaWelcomeMessage) {
            qaWelcomeMessage.style.display = 'none';
        }
        
        // 添加用户消息
        addQAMessage('user', question);
        
        // 清空输入框
        if (questionInput) {
            questionInput.value = '';
        }
        
        // 添加AI等待消息（正在思考...）
        const aiMessageId = 'ai-msg-' + Date.now();
        addQAMessage('ai', '', false, aiMessageId);
        
        // 调用问答API（流式）
        const response = await fetch('/api/video-qa-stream', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                question: question,
                transcript: qaState.transcript,
                video_url: qaState.videoInfo?.webpage_url || ''
            })
        });
        
        if (!response.ok) {
            throw new Error('问答请求失败');
        }
        
        // 处理流式响应
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let aiAnswer = '';
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');
            
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        if (data.content) {
                            aiAnswer += data.content;
                            updateQAMessage(aiMessageId, aiAnswer);
                        }
                        if (data.done) {
                            updateQAMessage(aiMessageId, aiAnswer);
                        }
                        if (data.error) {
                            throw new Error(data.error);
                        }
                    } catch (e) {
                        console.error('解析流数据失败:', e);
                    }
                }
            }
        }
        
        // 保存到对话历史
        qaState.conversationHistory.push({
            question: question,
            answer: aiAnswer,
            timestamp: new Date().toISOString()
        });
        
    } catch (error) {
        console.error('提问失败:', error);
        alert(`提问失败: ${error.message}`);
    }
}

function addQAMessage(type, content, isTyping = false, messageId = null) {
    const container = document.getElementById('messagesContainer');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message message-${type}`;
    
    // 如果提供了messageId，设置ID以便后续更新
    if (messageId) {
        messageDiv.id = messageId;
    }
    
    const time = new Date().toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit'
    });
    
    if (type === 'user') {
        messageDiv.innerHTML = `
            <div class="message-avatar">
                <img src="/static/zlab.jpeg" alt="翟星人" style="width: 100%; height: 100%; object-fit: cover; border-radius: 50%;">
            </div>
            <div class="message-content">
                <div class="message-name" style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 4px; font-weight: 600;">翟星人</div>
                <div class="message-bubble">${content}</div>
                <div class="message-time">${time}</div>
            </div>
        `;
    } else {
        if (isTyping) {
            messageDiv.innerHTML = `
                <div class="message-avatar">
                    <img src="/static/product-logo.png" alt="ViNote" style="width: 100%; height: 100%; object-fit: cover; border-radius: 50%;">
                </div>
                <div class="message-content">
                    <div class="message-name" style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 4px; font-weight: 600;">ViNote</div>
                    <div class="message-bubble">
                        <div class="typing-indicator">
                            <div class="typing-dot"></div>
                            <div class="typing-dot"></div>
                            <div class="typing-dot"></div>
                        </div>
                    </div>
                </div>
            `;
        } else {
            // 🔥 保留换行，不使用Markdown渲染
            const formattedContent = content.replace(/\n/g, '<br>');
            messageDiv.innerHTML = `
                <div class="message-avatar">
                    <img src="/static/product-logo.png" alt="ViNote" style="width: 100%; height: 100%; object-fit: cover; border-radius: 50%;">
                </div>
                <div class="message-content">
                    <div class="message-name" style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 4px; font-weight: 600;">ViNote</div>
                    <div class="message-bubble">${formattedContent || '<span style="opacity: 0.5;">正在思考...</span>'}</div>
                    <div class="message-time">${time}</div>
                </div>
            `;
        }
    }
    
    container.appendChild(messageDiv);
    
    // 滚动到底部
    container.scrollTop = container.scrollHeight;
    
    return messageId;
}

function updateQAMessage(messageId, content) {
    const messageDiv = document.getElementById(messageId);
    if (!messageDiv) return;
    
    const bubble = messageDiv.querySelector('.message-bubble');
    if (bubble) {
        // 🔥 使用marked.js渲染Markdown内容
        if (typeof marked !== 'undefined' && content) {
            marked.setOptions({
                breaks: true,  // 支持GFM换行
                gfm: true,     // 启用GitHub风格的Markdown
            });
            bubble.innerHTML = marked.parse(content);
        } else {
            // 降级方案：保留换行
            const formattedContent = content.replace(/\n/g, '<br>');
            bubble.innerHTML = formattedContent || '<span style="opacity: 0.5;">正在思考...</span>';
        }
    }
    
    // 滚动到底部
    const container = document.getElementById('messagesContainer');
    if (container) {
        container.scrollTop = container.scrollHeight;
    }
}

function clearQAConversation() {
    if (!confirm('确定要清空对话历史吗？')) {
        return;
    }
    
    qaState.conversationHistory = [];
    
    const messagesContainer = document.getElementById('messagesContainer');
    const qaWelcomeMessage = document.getElementById('qaWelcomeMessage');
    
    if (messagesContainer) {
        messagesContainer.innerHTML = '';
        messagesContainer.style.display = 'none';
    }
    if (qaWelcomeMessage) {
        qaWelcomeMessage.style.display = 'block';
    }
}

// 页面状态缓存函数
function savePageState() {
    try {
        const state = {
            currentPage: getCurrentActivePage(),
            notesPage: app ? { videoInfo: app.currentVideoInfo, videoUrl: app.videoUrl?.value, summaryLanguage: app.summaryLanguage?.value } : null,
            timestamp: Date.now()
        };
        sessionStorage.setItem('viNotePageState', JSON.stringify(state));
    } catch (error) {
        console.error('保存页面状态失败:', error);
    }
}

function restorePageState() {
    try {
        const stateStr = sessionStorage.getItem('viNotePageState');
        if (!stateStr) return;
        const state = JSON.parse(stateStr);
        if (Date.now() - state.timestamp > 3600000) {
            sessionStorage.removeItem('viNotePageState');
            return;
        }
        if (state.currentPage && state.currentPage !== 'landingPage') {
            const pageType = Object.keys(workspacePages).find(key => workspacePages[key] === state.currentPage);
            if (pageType) {
                const targetPage = document.getElementById(state.currentPage);
                if (targetPage) {
                    document.getElementById('landingPage').style.display = 'none';
                    targetPage.style.display = 'grid';
                    if (pageType === 'notes' && state.notesPage && app) {
                        if (state.notesPage.videoUrl && app.videoUrl) app.videoUrl.value = state.notesPage.videoUrl;
                        if (state.notesPage.videoInfo) {
                            app.currentVideoInfo = state.notesPage.videoInfo;
                            app.displayVideoPreview(state.notesPage.videoInfo);
                        }
                    }
                }
            }
        }
    } catch (error) {
        console.error('恢复页面状态失败:', error);
    }
}

function getCurrentActivePage() {
    if (document.getElementById('landingPage').style.display !== 'none') return 'landingPage';
    for (const pageId of Object.values(workspacePages)) {
        const page = document.getElementById(pageId);
        if (page && page.style.display !== 'none') return pageId;
    }
    return 'landingPage';
}

function clearPageStateCache() {
    try {
        sessionStorage.removeItem('viNotePageState');
    } catch (error) {
        console.error('清除缓存失败:', error);
    }
}

// 🔥 清除所有工作区状态
function clearAllWorkspaceStates() {
    // 清除QA状态
    qaState = {
        videoInfo: null,
        transcript: null,
        taskId: null,
        eventSource: null,
        conversationHistory: []
    };
    
    // 关闭任何活跃的SSE连接
    if (qaState.eventSource) {
        qaState.eventSource.close();
        qaState.eventSource = null;
    }
    
    // 清除全局标志
    window.qaPreviewingInProgress = false;
    window.qaCurrentTaskId = null;
    window.qaTranscript = null;
    
    // 清除笔记页面状态
    if (app) {
        app.currentVideoInfo = null;
        app.currentTaskId = null;
        app.currentDownloadId = null;
    }
    
    console.log('✅ 所有工作区状态已清除');
}

console.log('✅ 工具函数模块已加载');
