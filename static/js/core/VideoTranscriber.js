/**
 * VideoTranscriber 核心类
 * 负责视频转录和笔记生成的主要逻辑
 */
class VideoTranscriber {
    constructor() {
        this.apiBase = '/api';
        this.currentTaskId = null;
        this.currentDownloadId = null;
        this.eventSource = null;
        this.downloadEventSource = null;
        this.currentLanguage = 'zh';
        this.currentVideoInfo = null;
        this.selectedQuality = null;

        // DOM元素引用
        this.initializeElements();
        
        // 初始化
        this.initializeApp();
    }

    initializeElements() {
        // 表单元素
        this.videoUrl = document.getElementById('videoUrl');
        this.summaryLanguage = document.getElementById('summaryLanguage');
        
        // 加载容器
        this.loadingContainer = document.getElementById('loadingContainer');
        
        // 预览区域
        this.videoPreview = document.getElementById('videoPreview');
        this.videoTitle = document.getElementById('videoTitle');
        this.videoDescription = document.getElementById('videoDescription');
        this.videoMeta = document.getElementById('videoMeta');
        this.videoPlayer = document.getElementById('videoPlayer');
        
        // 进度区域
        this.progressSection = document.getElementById('progressSection');
        this.progressStatus = document.getElementById('progressStatus');
        this.progressFill = document.getElementById('progressFill');
        
        // 下载进度区域
        this.downloadSection = document.getElementById('downloadSection');
        this.downloadStatus = document.getElementById('downloadStatus');
        this.downloadProgressFill = document.getElementById('downloadProgressFill');
        this.downloadSpeed = document.getElementById('downloadSpeed');
        this.downloadETA = document.getElementById('downloadETA');
        this.downloadSize = document.getElementById('downloadSize');
        this.downloadMessage = document.getElementById('downloadMessage');
        
        // 结果区域
        this.resultsSection = document.getElementById('resultsSection');
        this.transcriptContent = document.getElementById('transcriptContent');
        this.summaryContent = document.getElementById('summaryContent');
        this.rawContent = document.getElementById('rawContent');
        this.translationContent = document.getElementById('translationContent');
        this.rawTab = document.getElementById('rawTab');
        this.translationTab = document.getElementById('translationTab');
        
        // 模态框
        this.downloadModal = document.getElementById('downloadModal');
        this.qualityOptions = document.getElementById('qualityOptions');
        
        // 消息区域
        this.errorMessage = document.getElementById('errorMessage');
        this.successMessage = document.getElementById('successMessage');
        
        // 语言切换
        this.langText = document.getElementById('langText');
    }

    initializeApp() {
        // 设置事件监听
        this.setupEventListeners();
        
        // 初始化多语言
        this.updateLanguage();
        
        // 初始化时禁用转录和下载按钮
        this.disableActionButtons();
        
        console.log('AI视频笔记已初始化');
    }

    setupEventListeners() {
        // 表单提交监听 - 阻止默认表单提交
        const form = document.getElementById('videoForm');
        if (form) {
            form.addEventListener('submit', (e) => {
                e.preventDefault();
                console.log('表单提交被阻止');
                return false;
            });
        }
        
        // URL输入框回车监听
        if (this.videoUrl) {
            this.videoUrl.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    this.previewVideo();
                }
            });
            
            // URL改变时禁用按钮
            this.videoUrl.addEventListener('input', () => {
                this.disableActionButtons();
                // 清空当前视频信息
                this.currentVideoInfo = null;
            });
        }
        
        // 模态框点击外部关闭
        if (this.downloadModal) {
            this.downloadModal.addEventListener('click', (e) => {
                if (e.target === this.downloadModal) {
                    this.closeDownloadModal();
                }
            });
        }
    }

    // 智能提取URL（处理B站等分享文本）
    extractUrl(text) {
        if (!text) return null;
        
        // 匹配URL的正则表达式
        const urlPattern = /(https?:\/\/[^\s]+)/i;
        const match = text.match(urlPattern);
        
        if (match) {
            // 提取到URL，清理可能的尾部字符
            let url = match[0];
            // 移除可能的尾部符号（如中文标点、括号等）
            url = url.replace(/[】」\)）]+$/, '');
            console.log('从分享文本中提取URL:', url);
            
            // 更新输入框为纯URL（用户体验更好）
            this.videoUrl.value = url;
            
            return url;
        }
        
        // 如果没有匹配到URL，检查是否本身就是URL
        if (text.startsWith('http://') || text.startsWith('https://')) {
            return text;
        }
        
        return null;
    }

    isEmbeddable(url) {
        // 检测支持嵌入播放的平台：YouTube 和 Bilibili
        return url && (
            url.includes('youtube.com') || 
            url.includes('youtu.be') ||
            url.includes('bilibili.com') ||
            url.includes('b23.tv')  // B站短链接
        );
    }

    // 多语言支持
    toggleLanguage() {
        this.currentLanguage = this.currentLanguage === 'zh' ? 'en' : 'zh';
        this.updateLanguage();
        this.langText.textContent = this.currentLanguage === 'zh' ? '中文' : 'English';
    }

    updateLanguage() {
        const elements = document.querySelectorAll('[data-zh], [data-en]');
        elements.forEach(element => {
            const text = element.getAttribute(`data-${this.currentLanguage}`);
            if (text) {
                element.textContent = text;
            }
        });

        // 更新placeholder
        const placeholderElements = document.querySelectorAll('[data-zh-placeholder], [data-en-placeholder]');
        placeholderElements.forEach(element => {
            const placeholder = element.getAttribute(`data-${this.currentLanguage}-placeholder`);
            if (placeholder) {
                element.placeholder = placeholder;
            }
        });
    }

    // 按钮状态控制
    enableActionButtons() {
        const transcribeBtn = document.getElementById('transcribeBtn');
        const downloadBtn = document.getElementById('downloadBtn');
        
        if (transcribeBtn) {
            transcribeBtn.disabled = false;
            transcribeBtn.style.opacity = '1';
            transcribeBtn.style.cursor = 'pointer';
        }
        
        if (downloadBtn) {
            downloadBtn.disabled = false;
            downloadBtn.style.opacity = '1';
            downloadBtn.style.cursor = 'pointer';
        }
        
        console.log('生成笔记和下载按钮已启用');
    }
    
    disableActionButtons() {
        const transcribeBtn = document.getElementById('transcribeBtn');
        const downloadBtn = document.getElementById('downloadBtn');
        
        if (transcribeBtn) {
            transcribeBtn.disabled = true;
            transcribeBtn.style.opacity = '0.5';
            transcribeBtn.style.cursor = 'not-allowed';
        }
        
        if (downloadBtn) {
            downloadBtn.disabled = true;
            downloadBtn.style.opacity = '0.5';
            downloadBtn.style.cursor = 'not-allowed';
        }
        
        console.log('生成笔记和下载按钮已禁用');
    }

    formatBytes(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
}
