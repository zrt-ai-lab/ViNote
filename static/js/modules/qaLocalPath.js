/**
 * 视频问答 - 本地路径处理模块
 */

// 问答模式输入切换
function switchQAInputMode(mode) {
    const urlModeBtn = document.getElementById('qaUrlModeBtn');
    const pathModeBtn = document.getElementById('qaPathModeBtn');
    const urlInputSection = document.getElementById('qaUrlInputSection');
    const localPathSection = document.getElementById('qaLocalPathSection');
    
    if (mode === 'url') {
        urlModeBtn.style.background = 'rgba(255, 255, 255, 0.1)';
        urlModeBtn.style.color = 'white';
        pathModeBtn.style.background = 'transparent';
        pathModeBtn.style.color = 'var(--text-secondary)';
        
        urlInputSection.style.display = 'block';
        localPathSection.style.display = 'none';
    } else {
        urlModeBtn.style.background = 'transparent';
        urlModeBtn.style.color = 'var(--text-secondary)';
        pathModeBtn.style.background = 'rgba(255, 255, 255, 0.1)';
        pathModeBtn.style.color = 'white';
        
        urlInputSection.style.display = 'none';
        localPathSection.style.display = 'block';
    }
}

// 预览本地视频(问答模式)
async function previewLocalVideoForQA() {
    const pathInput = document.getElementById('qaLocalVideoPath');
    const filePath = pathInput?.value?.trim();
    
    if (!filePath) {
        alert('请输入本地视频文件路径');
        return;
    }
    
    // 验证路径格式
    const validExtensions = ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.mp3', '.wav', '.m4a', '.aac', '.ogg'];
    const hasValidExt = validExtensions.some(ext => filePath.toLowerCase().endsWith(ext));
    
    if (!hasValidExt) {
        alert('请输入有效的视频或音频文件路径\n支持格式: MP4, AVI, MOV, MKV, MP3, WAV 等');
        return;
    }
    
    // 验证是否为绝对路径
    const isAbsolutePath = filePath.startsWith('/') || /^[A-Za-z]:\\/.test(filePath) || filePath.startsWith('\\\\');
    if (!isAbsolutePath) {
        alert('请输入绝对路径(完整路径)\n\n示例:\n- Mac/Linux: /Users/zhangsan/Videos/video.mp4\n- Windows: C:\\Users\\zhangsan\\Videos\\video.mp4');
        return;
    }
    
    // 显示文件信息
    const emptyState = document.getElementById('qaEmptyState');
    if (emptyState) emptyState.style.display = 'none';
    
    const videoPreview = document.getElementById('qaVideoPreview');
    if (videoPreview) {
        videoPreview.style.display = 'block';
        videoPreview.classList.add('show');
        
        const videoPlayer = document.getElementById('qaVideoPlayer');
        if (videoPlayer) videoPlayer.style.display = 'none';
        
        const videoTitle = document.getElementById('qaVideoTitle');
        const videoMeta = document.getElementById('qaVideoMeta');
        
        const fileName = filePath.split('/').pop().split('\\').pop();
        
        if (videoTitle) {
            videoTitle.textContent = '本地文件: ' + fileName;
        }
        
        if (videoMeta) {
            const fileExt = filePath.split('.').pop().toLowerCase();
            const fileType = ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv'].includes('.' + fileExt) ? '视频文件' : '音频文件';
            
            videoMeta.innerHTML = `
                <div class="meta-item">
                    <div class="meta-label">文件类型</div>
                    <div class="meta-value">${fileType}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">文件格式</div>
                    <div class="meta-value">${fileExt.toUpperCase()}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">处理模式</div>
                    <div class="meta-value">本地路径</div>
                </div>
            `;
        }
    }
    
    // 启用预处理按钮
    const qaPreprocessBtn = document.getElementById('qaPreprocessBtn');
    if (qaPreprocessBtn) {
        qaPreprocessBtn.disabled = false;
    }
}

// 统一的预处理入口 - 根据当前模式调用对应函数
async function preprocessVideo() {
    // 检查当前是URL模式还是本地路径模式
    const urlSection = document.getElementById('qaUrlInputSection');
    const isUrlMode = urlSection && urlSection.style.display !== 'none';
    
    if (isUrlMode) {
        // URL模式 - 调用原有的预处理函数
        await preprocessVideoForQA();
    } else {
        // 本地路径模式
        await preprocessLocalVideoForQA();
    }
}

// 预处理本地视频(问答模式) - 使用transcribe-only API
async function preprocessLocalVideoForQA() {
    const pathInput = document.getElementById('qaLocalVideoPath');
    const filePath = pathInput?.value?.trim();
    
    if (!filePath) {
        alert('请输入本地视频文件路径');
        return;
    }
    
    const qaPreprocessBtn = document.getElementById('qaPreprocessBtn');
    const qaPreprocessBtnProgress = document.getElementById('qaPreprocessBtnProgress');
    const btnContent = qaPreprocessBtn?.querySelector('.btn-content');
    
    try {
        // 立即更新按钮状态
        if (qaPreprocessBtn && btnContent) {
            qaPreprocessBtn.classList.add('btn-downloading');
            qaPreprocessBtn.disabled = false;
            if (qaPreprocessBtnProgress) qaPreprocessBtnProgress.style.width = '0%';
            btnContent.innerHTML = `
                <i class="fas fa-times"></i>
                <span>取消预处理</span>
                <span id="qaPreprocessPercent" style="margin-left: 8px; font-size: 0.9em; opacity: 1;">0%</span>
            `;
        }
        
        // 调用transcribe-only API (使用FormData格式)
        const formData = new FormData();
        formData.append('file_path', filePath);
        
        const response = await fetch('/api/transcribe-only', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.detail || '预处理失败');
        }
        
        // 监控进度
        window.qaCurrentTaskId = data.task_id;
        monitorQAPreprocessProgress(data.task_id);
        
    } catch (error) {
        console.error('预处理失败:', error);
        const errorMsg = error.message || error.toString() || '未知错误';
        alert(`预处理失败: ${errorMsg}`);
        
        // 恢复按钮
        if (qaPreprocessBtn && btnContent) {
            qaPreprocessBtn.classList.remove('btn-downloading');
            qaPreprocessBtn.disabled = false;
            if (qaPreprocessBtnProgress) qaPreprocessBtnProgress.style.width = '0%';
            btnContent.innerHTML = `
                <i class="fas fa-cog"></i>
                <span>开始预处理</span>
                <span id="qaPreprocessPercent" style="margin-left: 8px; font-size: 0.9em; opacity: 0;">0%</span>
            `;
        }
    }
}

// 监控问答预处理进度
function monitorQAPreprocessProgress(taskId) {
    const eventSource = new EventSource(`/api/task-stream/${taskId}`);
    
    eventSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            
            if (data.type === 'heartbeat') return;
            
            const progress = data.progress || 0;
            
            // 更新按钮进度
            const qaPreprocessBtnProgress = document.getElementById('qaPreprocessBtnProgress');
            const qaPreprocessPercent = document.getElementById('qaPreprocessPercent');
            if (qaPreprocessBtnProgress) qaPreprocessBtnProgress.style.width = `${progress}%`;
            if (qaPreprocessPercent) qaPreprocessPercent.textContent = `${Math.round(progress)}%`;
            
            if (data.status === 'completed') {
                eventSource.close();
                onLocalQAPreprocessCompleted(data);
            } else if (data.status === 'error') {
                eventSource.close();
                alert(`预处理失败: ${data.error || '未知错误'}`);
                resetQAPreprocessButton();
            }
        } catch (error) {
            console.error('解析进度数据失败:', error);
        }
    };
    
    eventSource.onerror = () => {
        eventSource.close();
    };
}

// 预处理完成 - 本地路径模式特定处理
function onLocalQAPreprocessCompleted(data) {
    // 保存transcript供问答使用
    window.qaTranscript = data.transcript;
    
    // 调用全局的完成处理函数(在helpers.js中定义)
    // 这样可以复用UI更新和欢迎消息逻辑,避免重复
    if (typeof window.onQAPreprocessCompleted === 'function') {
        window.onQAPreprocessCompleted(data);
    }
}

// 重置预处理按钮
function resetQAPreprocessButton() {
    const qaPreprocessBtn = document.getElementById('qaPreprocessBtn');
    const qaPreprocessBtnProgress = document.getElementById('qaPreprocessBtnProgress');
    const btnContent = qaPreprocessBtn?.querySelector('.btn-content');
    
    if (qaPreprocessBtn && btnContent) {
        qaPreprocessBtn.classList.remove('btn-downloading');
        qaPreprocessBtn.disabled = false;
        if (qaPreprocessBtnProgress) qaPreprocessBtnProgress.style.width = '0%';
        btnContent.innerHTML = `
            <i class="fas fa-cog"></i>
            <span>开始预处理</span>
            <span id="qaPreprocessPercent" style="margin-left: 8px; font-size: 0.9em; opacity: 0;">0%</span>
        `;
    }
}

console.log('✅ 视频问答本地路径模块已加载');
