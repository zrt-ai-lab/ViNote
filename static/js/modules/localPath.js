/**
 * 本地路径处理模块
 * 处理本地视频文件路径输入和验证
 */

// 输入模式切换
function switchInputMode(mode) {
    const urlModeBtn = document.getElementById('urlModeBtn');
    const pathModeBtn = document.getElementById('pathModeBtn');
    const urlInputSection = document.getElementById('urlInputSection');
    const localPathSection = document.getElementById('localPathSection');
    
    if (mode === 'url') {
        // 切换到URL模式
        urlModeBtn.style.background = 'rgba(255, 255, 255, 0.1)';
        urlModeBtn.style.color = 'white';
        pathModeBtn.style.background = 'transparent';
        pathModeBtn.style.color = 'var(--text-secondary)';
        
        urlInputSection.style.display = 'block';
        localPathSection.style.display = 'none';
    } else {
        // 切换到路径模式
        urlModeBtn.style.background = 'transparent';
        urlModeBtn.style.color = 'var(--text-secondary)';
        pathModeBtn.style.background = 'rgba(255, 255, 255, 0.1)';
        pathModeBtn.style.color = 'white';
        
        urlInputSection.style.display = 'none';
        localPathSection.style.display = 'block';
    }
}

// 预览本地文件(仅显示信息,无法播放)
async function previewLocalVideo() {
    const pathInput = document.getElementById('localVideoPath');
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
    if (app) {
        const emptyState = document.getElementById('emptyState');
        if (emptyState) {
            emptyState.style.display = 'none';
        }
        
        const videoPreview = document.getElementById('videoPreview');
        if (videoPreview) {
            videoPreview.style.display = 'block';
            videoPreview.classList.add('show');
            
            // 隐藏视频播放器
            const videoPlayer = document.getElementById('videoPlayer');
            if (videoPlayer) videoPlayer.style.display = 'none';
            
            // 显示本地视频信息
            const videoTitle = document.getElementById('videoTitle');
            const videoDescription = document.getElementById('videoDescription');
            const videoMeta = document.getElementById('videoMeta');
            
            const fileName = filePath.split('/').pop().split('\\').pop();
            
            if (videoTitle) {
                videoTitle.textContent = '本地文件: ' + fileName;
                videoTitle.style.display = 'block';
            }
            
            if (videoDescription) {
                videoDescription.innerHTML = `
                    <div style="background: rgba(76, 140, 245, 0.08); padding: 16px; border-radius: 12px; border-left: 3px solid var(--accent-blue);">
                        <p style="margin: 0 0 8px 0; font-weight: 600; color: var(--text-primary);">
                            <i class="fas fa-info-circle" style="color: var(--accent-blue); margin-right: 6px;"></i>
                            本地文件信息
                        </p>
                        <p style="margin: 0; font-size: 0.9rem; color: var(--text-secondary); line-height: 1.6;">
                            📁 文件路径: <code style="background: rgba(0,0,0,0.2); padding: 2px 6px; border-radius: 4px; font-size: 0.85em;">${filePath}</code><br>
                            💡 提示: 浏览器无法直接播放本地文件,点击下方"生成笔记"开始处理
                        </p>
                    </div>
                `;
                videoDescription.style.display = 'block';
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
                videoMeta.style.display = 'grid';
            }
        }
        
        // 启用生成笔记按钮
        const localTranscribeBtn = document.getElementById('localTranscribeBtn');
        if (localTranscribeBtn) {
            localTranscribeBtn.disabled = false;
        }
    }
}

// 处理本地视频 - 使用统一的转录流程
async function processLocalVideo() {
    // 如果正在生成中，点击则取消任务
    if (window.transcriptionInProgress && app && app.currentTaskId) {
        console.log('点击取消生成(本地路径模式)');
        app.cancelTask();
        return;
    }
    
    // 防止重复点击
    if (window.transcriptionInProgress) {
        console.log('正在生成笔记中，忽略重复点击');
        return;
    }
    
    const pathInput = document.getElementById('localVideoPath');
    const languageSelect = document.getElementById('localSummaryLanguage');
    
    const filePath = pathInput?.value?.trim();
    const language = languageSelect?.value || 'zh';
    
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
    
    // 立即设置标志
    window.transcriptionInProgress = true;
    console.log('✅ 设置转录进行中标志(本地路径模式)');
    
    try {
        // 隐藏预览和结果区域
        if (app) {
            app.hideResults();
        }
        
        // 立即更新本地按钮状态为处理中
        const localTranscribeBtn = document.getElementById('localTranscribeBtn');
        const localProgressBg = document.getElementById('localTranscribeBtnProgress');
        const localBtnContent = localTranscribeBtn?.querySelector('.btn-content');
        
        if (localTranscribeBtn && localBtnContent) {
            localTranscribeBtn.classList.add('btn-downloading');
            localTranscribeBtn.disabled = false;
            if (localProgressBg) localProgressBg.style.width = '0%';
            localBtnContent.innerHTML = `
                <i class="fas fa-times"></i>
                <span>取消生成</span>
                <span id="localTranscribePercent" style="margin-left: 8px; font-size: 0.9em; opacity: 1; transition: opacity 0.3s;">0%</span>
            `;
        }
        
        // 显示进度区域
        if (app) {
            app.showProgress();
        }
        
        // 调用后端API
        const response = await fetch('/api/process-local-path', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                file_path: filePath,
                language: language
            })
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.detail || '处理失败');
        }
        
        // 开始监控任务进度
        if (app) {
            app.currentTaskId = data.task_id;
            app.startProgressStream();
        }
        
    } catch (error) {
        console.error('处理本地视频失败:', error);
        
        // 重置标志
        window.transcriptionInProgress = false;
        console.log('✅ 重置转录标志(本地路径模式-错误)');
        
        if (app) {
            app.hideProgress();
            app.showError(`处理失败: ${error.message}`);
        } else {
            alert(`处理失败: ${error.message}`);
        }
    }
}

console.log('✅ 本地路径处理模块已加载');
