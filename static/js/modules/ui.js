/**
 * UI交互模块
 * 负责消息提示、加载动画等UI交互
 */

Object.assign(VideoTranscriber.prototype, {
    // 消息显示
    showError(message) {
        this.hideMessages();
        this.errorMessage.textContent = message;
        this.errorMessage.style.display = 'block';
        this.errorMessage.scrollIntoView({ behavior: 'smooth', block: 'center' });
        
        // 5秒后自动隐藏
        setTimeout(() => {
            this.errorMessage.style.display = 'none';
        }, 5000);
    },

    showSuccess(message) {
        this.hideMessages();
        this.successMessage.textContent = message;
        this.successMessage.style.display = 'block';
        
        // 3秒后自动隐藏
        setTimeout(() => {
            this.successMessage.style.display = 'none';
        }, 3000);
    },

    hideMessages() {
        this.errorMessage.style.display = 'none';
        this.successMessage.style.display = 'none';
    },

    showLoading(title, message) {
        // 隐藏暂无视频占位
        const emptyState = document.getElementById('emptyState');
        if (emptyState) {
            emptyState.style.display = 'none';
        }
        
        // 隐藏其他区域
        if (this.videoPreview) this.videoPreview.style.display = 'none';
        if (this.progressSection) this.progressSection.style.display = 'none';
        if (this.downloadSection) this.downloadSection.style.display = 'none';
        if (this.resultsSection) this.resultsSection.style.display = 'none';
        
        // 显示加载动画
        if (this.loadingContainer) {
            this.loadingContainer.classList.add('show');
            
            // 更新加载文本
            const loadingText = this.loadingContainer.querySelector('.loading-text');
            const loadingSubtext = this.loadingContainer.querySelector('.loading-subtext');
            if (loadingText) loadingText.textContent = message || '正在处理...';
            if (loadingSubtext) loadingSubtext.textContent = '请稍候片刻';
        }
    },

    hideLoading() {
        // 隐藏加载动画
        this.loadingContainer.classList.remove('show');
    },

    showDownloadProgress() {
        this.downloadSection.style.display = 'block';
        this.downloadSection.classList.add('fade-in');
        this.resetDownloadProgress();
        this.downloadSection.scrollIntoView({ behavior: 'smooth', block: 'center' });
    },

    hideDownloadProgress() {
        this.downloadSection.style.display = 'none';
        this.stopDownloadStream();
    },

    resetDownloadProgress() {
        this.downloadStatus.textContent = '0%';
        this.downloadProgressFill.style.width = '0%';
        this.downloadSpeed.textContent = '速度: 0MB/s';
        this.downloadETA.textContent = '剩余: --:--';
        this.downloadSize.textContent = '大小: 0MB / 0MB';
        this.downloadMessage.textContent = '正在下载...';
    },

    // 标签页切换
    showTab(tabName) {
        // 移除所有活跃状态
        document.querySelectorAll('.tab-button').forEach(btn => btn.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
        
        // 激活选中的标签页
        document.querySelector(`[onclick="showTab('${tabName}')"]`).classList.add('active');
        document.getElementById(`${tabName}Content`).classList.add('active');
    }
});

console.log('✅ UI模块已加载');
