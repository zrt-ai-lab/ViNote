/**
 * 进度管理模块
 * 负责进度显示、日志、按钮状态等
 */

Object.assign(VideoTranscriber.prototype, {
    showProgress() {
        if (!this.progressSection) {
            console.error('进度区域元素不存在');
            return;
        }
        this.progressSection.style.display = 'block';
        this.progressSection.classList.add('show');
        this.resetProgress();
        this.resetStepProgress();
        this.updateStepProgress('download', false);
        this.updateTranscribeButtonState('processing', 0);
        this.progressSection.scrollIntoView({ behavior: 'smooth', block: 'center' });
    },

    hideProgress() {
        if (this.progressSection) {
            this.progressSection.style.display = 'none';
        }
        this.stopProgressStream();
    },

    resetProgress() {
        const progressMessage = document.getElementById('progressMessage');
        if (progressMessage) {
            progressMessage.textContent = '准备开始...';
            progressMessage.style.color = 'var(--text-secondary)';
        }
        if (this.logContainer) {
            this.logContainer.remove();
            this.logContainer = null;
        }
    },

    appendLog(logData) {
        return;
    },

    updateStepProgress(stepName, isCompleted = false) {
        const step = document.querySelector(`.progress-step[data-step="${stepName}"]`);
        if (!step) return;
        
        const allSteps = document.querySelectorAll('.progress-step');
        const stepIndex = Array.from(allSteps).indexOf(step);
        
        if (isCompleted) {
            step.classList.remove('active');
            step.classList.add('completed');
            if (stepIndex < allSteps.length - 1) {
                const nextStep = allSteps[stepIndex + 1];
                if (!nextStep.classList.contains('active') && !nextStep.classList.contains('completed')) {
                    nextStep.classList.add('active');
                }
            }
        } else {
            for (let i = 0; i < stepIndex; i++) {
                allSteps[i].classList.remove('active');
                allSteps[i].classList.add('completed');
            }
            step.classList.add('active');
            step.classList.remove('completed');
            for (let i = stepIndex + 1; i < allSteps.length; i++) {
                allSteps[i].classList.remove('active', 'completed');
            }
        }
    },

    updateStepProgressByMessage(message, progress) {
        let stepName = null;
        let isCompleted = false;
        
        if (message.includes('下载') || message.includes('音频') || message.includes('获取视频')) {
            stepName = 'download';
            isCompleted = message.includes('完成') || message.includes('成功');
        } else if (message.includes('转录') || message.includes('语音识别') || message.includes('原文转录') || message.includes('提取语音')) {
            stepName = 'transcribe';
            isCompleted = message.includes('完成') || message.includes('成功');
        } else if (message.includes('优化') || message.includes('美化') || message.includes('整理') || message.includes('完整笔记') || message.includes('智能提取')) {
            stepName = 'optimize';
            isCompleted = message.includes('完成') || message.includes('成功');
        } else if (message.includes('摘要') || message.includes('总结') || message.includes('提炼') || message.includes('精华')) {
            stepName = 'summarize';
            isCompleted = message.includes('完成') || message.includes('成功') || progress >= 95;
        }
        
        if (progress >= 100) {
            ['download', 'transcribe', 'optimize', 'summarize'].forEach(step => {
                this.updateStepProgress(step, true);
            });
            this.updateStepProgress('complete', true);
            return;
        }
        
        if (stepName) {
            this.updateStepProgress(stepName, isCompleted);
        }
    },

    resetStepProgress() {
        const steps = document.querySelectorAll('.progress-step');
        steps.forEach(step => {
            step.classList.remove('active', 'completed');
        });
    },

    updateStepDescription(stepName, message) {
        const step = document.querySelector(`.progress-step[data-step="${stepName}"]`);
        if (!step) return;
        const description = step.querySelector('.step-description');
        if (description) {
            description.textContent = message;
        }
    },

    updateTranscribeButtonState(state, progress = 0) {
        // 支持URL模式和本地路径模式的按钮
        const transcribeBtn = document.getElementById('transcribeBtn');
        const localTranscribeBtn = document.getElementById('localTranscribeBtn');
        
        // 获取当前激活的按钮
        const activeBtn = transcribeBtn && transcribeBtn.offsetParent !== null ? transcribeBtn : localTranscribeBtn;
        if (!activeBtn) return;
        
        // 获取对应的进度条和百分比元素
        const isLocalMode = activeBtn.id === 'localTranscribeBtn';
        const progressBg = document.getElementById(isLocalMode ? 'localTranscribeBtnProgress' : 'transcribeBtnProgress');
        const btnContent = activeBtn.querySelector('.btn-content');
        const percentElem = document.getElementById(isLocalMode ? 'localTranscribePercent' : 'transcribePercent');
        
        const percentId = isLocalMode ? 'localTranscribePercent' : 'transcribePercent';
        
        if (state === 'processing') {
            activeBtn.classList.add('btn-downloading');
            activeBtn.disabled = false;
            if (progressBg) progressBg.style.width = `${progress}%`;
            if (percentElem) {
                percentElem.style.opacity = '1';
                percentElem.textContent = `${Math.round(progress)}%`;
            }
            if (btnContent) {
                btnContent.innerHTML = `
                    <i class="fas fa-times"></i>
                    <span>取消生成</span>
                    <span id="${percentId}" style="margin-left: 8px; font-size: 0.9em; opacity: 1; transition: opacity 0.3s;">${Math.round(progress)}%</span>
                `;
            }
        } else if (state === 'completed') {
            activeBtn.classList.remove('btn-downloading');
            activeBtn.disabled = true;
            if (progressBg) progressBg.style.width = '100%';
            if (percentElem) percentElem.style.opacity = '0';
            if (btnContent) {
                btnContent.innerHTML = `
                    <i class="fas fa-check"></i>
                    <span>生成完成</span>
                    <span id="${percentId}" style="margin-left: 8px; font-size: 0.9em; opacity: 0; transition: opacity 0.3s;">0%</span>
                `;
            }
        } else {
            activeBtn.classList.remove('btn-downloading');
            activeBtn.disabled = false;
            if (progressBg) progressBg.style.width = '0%';
            if (percentElem) {
                percentElem.style.opacity = '0';
                percentElem.textContent = '0%';
            }
            if (btnContent) {
                btnContent.innerHTML = `
                    <i class="fas fa-magic"></i>
                    <span>生成笔记</span>
                    <span id="${percentId}" style="margin-left: 8px; font-size: 0.9em; opacity: 0; transition: opacity 0.3s;">0%</span>
                `;
            }
        }
    },

    updateDownloadButtonState(state, progress = 0) {
        const downloadBtn = document.getElementById('downloadBtn');
        const progressBg = document.getElementById('downloadBtnProgress');
        const btnContent = downloadBtn.querySelector('.btn-content');
        
        if (state === 'downloading') {
            downloadBtn.classList.add('btn-downloading');
            progressBg.style.width = `${progress}%`;
            btnContent.innerHTML = `
                <i class="fas fa-times"></i>
                <span>取消下载</span>
            `;
        } else if (state === 'completed') {
            downloadBtn.classList.remove('btn-downloading');
            progressBg.style.width = '100%';
            btnContent.innerHTML = `
                <i class="fas fa-check"></i>
                <span>下载完成</span>
            `;
        } else {
            downloadBtn.classList.remove('btn-downloading');
            progressBg.style.width = '0%';
            btnContent.innerHTML = `
                <i class="fas fa-download"></i>
                <span>下载视频</span>
            `;
        }
    }
});

console.log('✅ 进度管理模块已加载');
