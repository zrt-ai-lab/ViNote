/**
 * 视频预览模块
 * 负责视频信息的预览和显示
 */

// 扩展 VideoTranscriber 类的视频预览功能
Object.assign(VideoTranscriber.prototype, {
    // 视频预览功能
    async previewVideo() {
        // 如果正在生成笔记,禁止预览
        if (window.transcriptionInProgress) {
            console.log('正在生成笔记中,禁止预览');
            return;
        }
        
        // 防止重复点击
        if (window.previewingInProgress) {
            console.log('正在预览中，忽略重复点击');
            return;
        }
        
        let url = this.videoUrl.value.trim();
        if (!url) {
            this.showError('请输入视频链接');
            return;
        }

        // 智能提取URL：处理B站等平台的分享文本
        url = this.extractUrl(url);
        if (!url) {
            this.showError('未能识别有效的视频链接');
            return;
        }

        // 立即设置标志
        window.previewingInProgress = true;
        console.log('✅ 设置预览进行中标志');

        try {
            // 先隐藏旧的预览内容，避免显示之前的数据
            if (this.videoPreview) {
                this.videoPreview.style.display = 'none';
                this.videoPreview.classList.remove('show');
            }
            
            // 更新预览按钮为加载中状态
            this.updatePreviewButtonState('loading');
            
            this.showLoading('预览视频', '正在获取视频信息...');
            
            const response = await fetch(`${this.apiBase}/preview-video?url=${encodeURIComponent(url)}`);
            const result = await response.json();

            console.log('预览API响应:', result);

            if (!response.ok) {
                throw new Error(result.detail || '预览失败');
            }

            // 处理响应数据
            if (result.success && result.data) {
                this.currentVideoInfo = result.data;
                this.displayVideoPreview(result.data);
                this.hideLoading();
                
                // 恢复预览按钮状态
                this.updatePreviewButtonState('idle');
                
                this.showSuccess('视频信息获取成功！');
            } else {
                throw new Error('返回数据格式错误');
            }
            
        } catch (error) {
            console.error('预览错误:', error);
            this.hideLoading();
            
            // 恢复预览按钮状态
            this.updatePreviewButtonState('idle');
            
            this.showError(`预览失败: ${error.message}`);
        } finally {
            // 重置标志，允许下次预览
            window.previewingInProgress = false;
            console.log('✅ 重置预览标志');
        }
    },

    displayVideoPreview(videoInfo) {
        console.log('开始显示视频预览，视频信息:', videoInfo);
        
        // 隐藏暂无视频占位
        const emptyState = document.getElementById('emptyState');
        if (emptyState) {
            emptyState.style.display = 'none';
        }
        
        // 显示预览区域
        this.videoPreview.style.display = 'block';
        this.videoPreview.classList.add('show');
        console.log('预览区域已设置为显示');
        
        // 预览成功后，启用转录和下载按钮
        this.enableActionButtons();
        
        // 构建视频内容HTML - 只添加播放器，不添加缩略图
        let playerHTML = '';
        
        // 添加播放器iframe（如果支持）
        if (videoInfo.embed_url && this.isEmbeddable(videoInfo.webpage_url)) {
            console.log('添加嵌入播放器:', videoInfo.embed_url);
            playerHTML = `<iframe src="${videoInfo.embed_url}" frameborder="0" allowfullscreen style="width: 100%; height: 400px; border-radius: 12px;"></iframe>`;
        } else {
            console.log('不支持嵌入播放');
        }
        
        // 一次性设置播放器HTML
        this.videoPlayer.innerHTML = playerHTML;
        
        // 设置标题和描述
        const title = videoInfo.title || '未知标题';
        const description = videoInfo.description || '无描述';
        console.log('设置标题:', title);
        console.log('设置描述:', description);
        
        this.videoTitle.textContent = title;
        this.videoDescription.textContent = description;
        
        // 生成元数据
        console.log('生成元数据...');
        this.generateVideoMeta(videoInfo);
        
        // 滚动到预览区域
        console.log('滚动到预览区域');
        this.videoPreview.scrollIntoView({ behavior: 'smooth', block: 'center' });
    },

    generateVideoMeta(videoInfo) {
        const metaItems = [
            { label: '时长', value: videoInfo.duration_string || '未知' },
            { label: '上传者', value: videoInfo.uploader || '未知' },
            { label: '观看次数', value: videoInfo.view_count_string || '0' },
            { label: '上传日期', value: videoInfo.upload_date || '未知' }
        ];

        this.videoMeta.innerHTML = metaItems.map(item => `
            <div class="meta-item">
                <div class="meta-label">${item.label}</div>
                <div class="meta-value">${item.value}</div>
            </div>
        `).join('');
    },

    // 更新预览按钮状态
    updatePreviewButtonState(state) {
        const previewBtn = document.getElementById('previewBtn');
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
                <span>预览视频</span>
            `;
        }
    }
});
