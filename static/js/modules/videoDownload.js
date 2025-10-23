/**
 * 视频下载模块
 * 负责视频下载功能
 */

Object.assign(VideoTranscriber.prototype, {
    handleDownloadClick() {
        const downloadBtn = document.getElementById('downloadBtn');
        if (downloadBtn.classList.contains('btn-downloading')) {
            this.cancelDownload();
        } else {
            this.showDownloadModal();
        }
    },

    showDownloadModal() {
        if (!this.currentVideoInfo) {
            this.showError('请先预览视频');
            return;
        }
        this.generateQualityOptions();
        this.downloadModal.style.display = 'block';
    },

    closeDownloadModal() {
        this.downloadModal.style.display = 'none';
        this.selectedQuality = null;
    },

    generateQualityOptions() {
        const formats = this.currentVideoInfo.formats || [];
        if (formats.length === 0) {
            this.qualityOptions.innerHTML = `
                <div class="quality-option" onclick="selectQuality('best')">
                    <div class="quality-label">最佳质量</div>
                    <div class="quality-size">自动选择</div>
                </div>
            `;
            return;
        }
        this.qualityOptions.innerHTML = formats.map(format => `
            <div class="quality-option" onclick="selectQuality('best[height<=${format.height}]')" 
                 data-quality="best[height<=${format.height}]">
                <div class="quality-label">${format.quality}</div>
                <div class="quality-size">${format.filesize_string}</div>
            </div>
        `).join('');
    },

    selectQuality(quality) {
        document.querySelectorAll('.quality-option').forEach(option => {
            option.classList.remove('selected');
        });
        const selectedOption = document.querySelector(`[data-quality="${quality}"]`) || 
                              document.querySelector('.quality-option');
        if (selectedOption) {
            selectedOption.classList.add('selected');
        }
        this.selectedQuality = quality;
    },

    async confirmDownload() {
        if (!this.selectedQuality) {
            this.showError('请选择下载质量');
            return;
        }
        const url = this.videoUrl.value.trim();
        try {
            this.closeDownloadModal();
            this.updateDownloadButtonState('downloading', 0);
            const response = await fetch(`${this.apiBase}/start-download`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: url, quality: this.selectedQuality })
            });
            const result = await response.json();
            if (!response.ok) {
                throw new Error(result.detail || '开始下载失败');
            }
            this.currentDownloadId = result.download_id;
            this.startDownloadStream();
        } catch (error) {
            this.updateDownloadButtonState('idle');
            this.showError(`开始下载失败: ${error.message}`);
        }
    },

    startDownloadStream() {
        if (this.downloadEventSource) {
            this.downloadEventSource.close();
        }
        this.downloadEventSource = new EventSource(`${this.apiBase}/download-stream/${this.currentDownloadId}`);
        this.downloadEventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.updateDownloadProgress(data);
            } catch (error) {
                console.error('解析下载SSE数据失败:', error);
            }
        };
        this.downloadEventSource.onerror = (error) => {
            console.error('下载SSE连接错误:', error);
            setTimeout(() => {
                if (this.currentDownloadId) {
                    this.startDownloadStream();
                }
            }, 3000);
        };
    },

    stopDownloadStream() {
        if (this.downloadEventSource) {
            this.downloadEventSource.close();
            this.downloadEventSource = null;
        }
    },

    updateDownloadProgress(data) {
        if (data.error) {
            this.onDownloadError({ error: data.error });
            return;
        }
        const progress = data.progress || 0;
        this.updateDownloadButtonState('downloading', progress);
        
        if (this.downloadSection && this.downloadSection.style.display !== 'none') {
            this.downloadStatus.textContent = `${Math.round(progress)}%`;
            this.downloadProgressFill.style.width = `${progress}%`;
            if (data.speed) {
                this.downloadSpeed.textContent = `速度: ${data.speed}`;
            }
            if (data.eta) {
                this.downloadETA.textContent = `剩余: ${data.eta}`;
            }
            if (data.downloaded_bytes && data.total_bytes) {
                const downloaded = this.formatBytes(data.downloaded_bytes);
                const total = this.formatBytes(data.total_bytes);
                this.downloadSize.textContent = `大小: ${downloaded} / ${total}`;
            }
            if (data.current_operation === 'downloading') {
                this.downloadMessage.textContent = '正在下载视频...';
            } else if (data.current_operation === 'processing') {
                this.downloadMessage.textContent = '正在处理视频...';
            } else if (data.current_operation === 'finalizing') {
                this.downloadMessage.textContent = '正在完成...';
            }
        }
        if (data.status === 'completed') {
            this.onDownloadCompleted(data);
        } else if (data.status === 'error') {
            this.onDownloadError(data);
        }
    },

    onDownloadCompleted(data) {
        this.stopDownloadStream();
        this.showSuccess('视频下载完成！点击下载文件...');
        this.updateDownloadButtonState('completed');
        window.location.href = `${this.apiBase}/get-download/${this.currentDownloadId}`;
        setTimeout(() => {
            this.updateDownloadButtonState('idle');
        }, 3000);
        this.currentDownloadId = null;
    },

    onDownloadError(data) {
        this.stopDownloadStream();
        this.showError(`下载失败: ${data.error || '未知错误'}`);
        this.updateDownloadButtonState('idle');
        this.currentDownloadId = null;
    },

    async cancelDownload() {
        if (!this.currentDownloadId) {
            this.showError('没有正在进行的下载任务');
            return;
        }
        try {
            const response = await fetch(`${this.apiBase}/cancel-download/${this.currentDownloadId}`, {
                method: 'DELETE'
            });
            const result = await response.json();
            if (response.ok) {
                this.stopDownloadStream();
                this.updateDownloadButtonState('idle');
                this.showSuccess('下载已取消');
                this.currentDownloadId = null;
            } else {
                throw new Error(result.detail || '取消失败');
            }
        } catch (error) {
            this.showError(`取消下载失败: ${error.message}`);
        }
    }
});

console.log('✅ 视频下载模块已加载');
