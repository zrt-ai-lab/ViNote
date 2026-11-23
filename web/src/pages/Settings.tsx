const SECTIONS = [
  { title: '模型', description: '选择生成摘要、问答等内容时使用的模型。' },
  { title: '语音转录', description: '选择转录引擎和模型。' },
  { title: '存储', description: '查看资产、生成产物和缓存的存储位置。' },
  { title: '导入目录', description: '查看允许从本地导入媒体的目录。' },
  { title: '高级诊断', description: '查看转录引擎、模型连接和存储状态。' },
];

export default function Settings() {
  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-8 sm:px-8 sm:py-12">
      <header>
        <h1 className="text-3xl font-bold tracking-tight">设置</h1>
        <p className="mt-2 text-sm text-[var(--color-text-secondary)]">以下是设置分区预览，暂不能查看或修改实际配置。</p>
      </header>

      <ul className="grid gap-3 sm:grid-cols-2">
        {SECTIONS.map(({ title, description }) => (
          <li key={title} className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
            <h2 className="font-semibold">{title}</h2>
            <p className="mt-2 text-sm text-[var(--color-text-secondary)]">{description}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
