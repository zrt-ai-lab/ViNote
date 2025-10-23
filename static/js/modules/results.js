/**
 * 结果显示模块
 * 负责显示和下载生成的内容
 */

Object.assign(VideoTranscriber.prototype, {
    displayResults(data) {
        this.resultsSection.style.display = 'block';
        this.resultsSection.classList.add('fade-in');
        
        if (typeof marked !== 'undefined') {
            const renderer = new marked.Renderer();
            const originalLinkRenderer = renderer.link;
            renderer.link = function(href, title, text) {
                const link = originalLinkRenderer.call(this, href, title, text);
                return link.replace('<a', '<a target="_blank" rel="noopener noreferrer"');
            };
            marked.setOptions({ breaks: true, gfm: true, renderer: renderer });
            
            this.transcriptContent.innerHTML = marked.parse(data.script || '');
            this.summaryContent.innerHTML = marked.parse(data.summary || '');
            if (data.raw_script) {
                this.rawContent.innerHTML = marked.parse(data.raw_script);
            }
            if (data.translation) {
                this.translationTab.style.display = 'block';
                this.translationContent.innerHTML = marked.parse(data.translation);
                this.currentResults.translation_filename = this.generateFilename(data, 'translation');
            }
        } else {
            this.transcriptContent.textContent = data.script || '';
            this.summaryContent.textContent = data.summary || '';
            if (data.raw_script) {
                this.rawContent.textContent = data.raw_script;
            }
            if (data.translation) {
                this.translationTab.style.display = 'block';
                this.translationContent.textContent = data.translation;
                this.currentResults.translation_filename = this.generateFilename(data, 'translation');
            }
        }
        
        this.currentResults = {
            transcript_filename: data.script_path ? data.script_path.split('/').pop() : this.generateFilename(data, 'transcript'),
            summary_filename: data.summary_path ? data.summary_path.split('/').pop() : this.generateFilename(data, 'summary'),
            raw_filename: data.raw_script_filename || null,
            translation_filename: data.translation_filename || null
        };
        
        this.resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    },

    generateFilename(data, type) {
        const shortId = data.short_id || 'unknown';
        const safeTitle = data.safe_title || 'video';
        return `${type}_${safeTitle}_${shortId}.md`;
    },

    hideResults() {
        if (this.resultsSection) {
            this.resultsSection.style.display = 'none';
        }
        if (this.translationTab) {
            this.translationTab.style.display = 'none';
        }
    },

    async downloadContent(type) {
        try {
            const filename = this.getDownloadFilename(type);
            if (!filename) {
                this.showError('文件不可用');
                return;
            }
            const link = document.createElement('a');
            link.href = `${this.apiBase}/download/${filename}`;
            link.download = filename;
            link.click();
        } catch (error) {
            this.showError(`下载失败: ${error.message}`);
        }
    },

    getDownloadFilename(type) {
        if (!this.currentResults) {
            console.error('没有当前结果数据');
            return null;
        }
        const filenameKey = `${type}_filename`;
        const filename = this.currentResults[filenameKey];
        return filename;
    }
});

console.log('✅ 结果显示模块已加载');
