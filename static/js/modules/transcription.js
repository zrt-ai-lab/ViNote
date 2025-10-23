/**
 * 转录功能模块
 * 负责视频转录和笔记生成
 */

Object.assign(VideoTranscriber.prototype, {
    // 开始转录
    async startTranscription() {
        // 如果正在生成中，点击则取消任务
        if (window.transcriptionInProgress && this.currentTaskId) {
            console.log('点击取消生成');
            this.cancelTask();
            return;
        }
        
        // 防止重复点击
        if (window.transcriptionInProgress) {
            console.log('正在生成笔记中，忽略重复点击');
            return;
        }
        
        const url = this.videoUrl.value.trim();
        const summaryLanguage = this.summaryLanguage.value;

        if (!url) {
            this.showError('请输入视频链接');
            return;
        }

        // 立即设置标志
        window.transcriptionInProgress = true;
        console.log('✅ 设置转录进行中标志');

        try {
            // 隐藏预览和结果区域
            this.hideResults();
            
            // 显示进度区域
            this.showProgress();
            
            const formData = new FormData();
            formData.append('url', url);
            formData.append('summary_language', summaryLanguage);

            const response = await fetch(`${this.apiBase}/process-video`, {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            if (!response.ok) {
                throw new Error(result.detail || '处理失败');
            }

            this.currentTaskId = result.task_id;
            this.startProgressStream();
            
        } catch (error) {
            this.hideProgress();
            this.showError(`开始转录失败: ${error.message}`);
        }
    },

    startProgressStream() {
        if (this.eventSource) {
            console.log('关闭旧的SSE连接');
            this.eventSource.close();
        }

        console.log(`创建新的SSE连接: task-stream/${this.currentTaskId}`);
        this.eventSource = new EventSource(`${this.apiBase}/task-stream/${this.currentTaskId}`);
        
        this.eventSource.onopen = () => {
            console.log('✅ SSE连接已建立');
        };
        
        this.eventSource.onmessage = (event) => {
            console.log('📨 收到原始SSE消息:', event.data);
            try {
                const data = JSON.parse(event.data);
                this.updateProgress(data);
            } catch (error) {
                console.error('❌ 解析SSE数据失败:', error, '原始数据:', event.data);
            }
        };

        this.eventSource.onerror = (error) => {
            console.error('❌ SSE连接错误:', error);
            console.log('EventSource readyState:', this.eventSource.readyState);
            console.log('0=CONNECTING, 1=OPEN, 2=CLOSED');
            
            // 不要立即重连，等待3秒
            setTimeout(() => {
                if (this.currentTaskId && this.eventSource.readyState === 2) {
                    console.log('🔄 尝试重新连接SSE...');
                    this.startProgressStream();
                }
            }, 3000);
        };
    },

    stopProgressStream() {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
    },

    updateProgress(data) {
        console.log('收到数据:', data);
        
        if (data.type === 'heartbeat') {
            return;
        }

        // 处理日志消息
        if (data.type === 'log') {
            this.appendLog(data);
            return;
        }

        // 更新进度
        const progress = data.progress || 0;
        
        // 更新按钮进度
        this.updateTranscribeButtonState('processing', progress);
        
        // 更新右侧进度消息
        const progressMessage = document.getElementById('progressMessage');
        if (progressMessage && data.message) {
            progressMessage.textContent = data.message;
        }
        
        // 在日志容器中显示消息（跳过100%的消息，由完成回调统一处理）
        if (data.message && progress < 100) {
            this.appendLog({
                level: 'INFO',
                message: data.message,
                timestamp: Date.now() / 1000
            });
        }
        
        // 根据消息内容更新步骤状态
        if (data.message) {
            this.updateStepProgressByMessage(data.message, progress);
        }

        // 检查状态
        if (data.status === 'completed') {
            this.onTranscriptionCompleted(data);
        } else if (data.status === 'error') {
            this.onTranscriptionError(data);
        }
    },

    onTranscriptionCompleted(data) {
        this.stopProgressStream();
        
        // 标记完成步骤为完成状态
        this.updateStepProgress('complete', true);
        
        // 更新进度消息为完成
        const progressMessage = document.getElementById('progressMessage');
        if (progressMessage) {
            progressMessage.textContent = '🎉 笔记生成完成！';
            progressMessage.style.color = 'var(--accent-green)';
        }
        
        // 在日志中添加完成消息
        this.appendLog({
            level: 'INFO',
            message: '🎉 笔记生成完成！',
            timestamp: Date.now() / 1000
        });
        
        // 更新按钮为完成状态
        this.updateTranscribeButtonState('completed');
        
        // 2秒后恢复按钮
        setTimeout(() => {
            this.updateTranscribeButtonState('idle');
        }, 2000);
        
        this.showSuccess('笔记生成完成！');
        this.displayResults(data);
        this.currentTaskId = null;
        
        // 重置标志
        window.transcriptionInProgress = false;
        console.log('✅ 重置转录标志');
    },

    onTranscriptionError(data) {
        this.stopProgressStream();
        this.hideProgress();
        
        // 恢复按钮状态
        this.updateTranscribeButtonState('idle');
        
        this.showError(`笔记生成失败: ${data.error || '未知错误'}`);
        this.currentTaskId = null;
        
        // 重置标志
        window.transcriptionInProgress = false;
        console.log('✅ 重置转录标志（错误）');
    },

    // 任务取消
    async cancelTask() {
        if (!this.currentTaskId) {
            return;
        }

        try {
            const response = await fetch(`${this.apiBase}/task/${this.currentTaskId}`, {
                method: 'DELETE'
            });

            if (response.ok) {
                this.stopProgressStream();
                this.hideProgress();
                
                // 恢复按钮状态
                this.updateTranscribeButtonState('idle');
                
                this.showSuccess('任务已取消');
                this.currentTaskId = null;
                
                // 重置标志
                window.transcriptionInProgress = false;
                console.log('✅ 重置转录标志（取消）');
            }
        } catch (error) {
            this.showError(`取消任务失败: ${error.message}`);
        }
    }
});

console.log('✅ 转录模块已加载');
