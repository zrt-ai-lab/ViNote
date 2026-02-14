import { useEffect, useRef } from 'react';
import { Transformer } from 'markmap-lib';
import { Markmap } from 'markmap-view';
import { ZoomIn, ZoomOut, Maximize2 } from 'lucide-react';

const transformer = new Transformer();

interface MarkmapViewProps {
  content: string;
  className?: string;
}

export default function MarkmapView({ content, className }: MarkmapViewProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const mmRef = useRef<Markmap | null>(null);

  useEffect(() => {
    if (!svgRef.current || !content) return;

    const { root } = transformer.transform(content);

    if (mmRef.current) {
      mmRef.current.setData(root);
      mmRef.current.fit();
    } else {
      mmRef.current = Markmap.create(svgRef.current, {
        autoFit: true,
        duration: 500,
      }, root);
    }
  }, [content]);

  useEffect(() => {
    return () => {
      if (mmRef.current) {
        mmRef.current.destroy();
        mmRef.current = null;
      }
    };
  }, []);

  const handleZoomIn = () => mmRef.current?.rescale(1.25);
  const handleZoomOut = () => mmRef.current?.rescale(0.8);
  const handleFit = () => mmRef.current?.fit();

  return (
    <div className={`relative w-full ${className || ''}`} style={{ minHeight: 400, height: '100%' }}>
      <style>{`
        .markmap-wrap svg text,
        .markmap-wrap svg foreignObject,
        .markmap-wrap svg foreignObject div,
        .markmap-wrap svg foreignObject span {
          color: var(--color-text) !important;
          fill: var(--color-text) !important;
          font-family: ui-sans-serif, system-ui, sans-serif !important;
          font-size: 14px !important;
        }
        .markmap-wrap svg path {
          stroke: var(--color-accent) !important;
          stroke-width: 2px;
          opacity: 0.6;
        }
        .markmap-wrap svg circle {
          stroke: var(--color-accent) !important;
          stroke-width: 2px;
          fill: var(--color-surface) !important;
        }
      `}</style>

      <div className="markmap-wrap w-full" style={{ height: '100%' }}>
        <svg ref={svgRef} style={{ width: '100%', height: '100%' }} />
      </div>

      <div className="absolute bottom-3 right-3 flex items-center gap-1.5 bg-[var(--color-surface)] border border-[var(--color-border)] p-1.5 rounded-lg shadow-sm">
        <button
          onClick={handleZoomIn}
          className="p-1.5 text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-bg)] rounded transition-colors"
          title="放大"
        >
          <ZoomIn size={14} />
        </button>
        <button
          onClick={handleZoomOut}
          className="p-1.5 text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-bg)] rounded transition-colors"
          title="缩小"
        >
          <ZoomOut size={14} />
        </button>
        <button
          onClick={handleFit}
          className="p-1.5 text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-bg)] rounded transition-colors"
          title="适应屏幕"
        >
          <Maximize2 size={14} />
        </button>
      </div>
    </div>
  );
}
