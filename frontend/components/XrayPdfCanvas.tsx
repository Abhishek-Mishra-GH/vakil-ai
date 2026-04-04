"use client";

import { useEffect, useRef, useState } from "react";

import type { Insight } from "@/lib/api";

type ReactPdfModule = typeof import("react-pdf");

let isPdfWorkerConfigured = false;

type XrayPdfCanvasProps = {
  currentPage: number;
  pdfUrl: string;
  zoom: number;
  selectedInsightId: string;
  visibleOverlays: Insight[];
  onLoadError: (message: string) => void;
  onLoadSuccess: (pageCount: number) => void;
  onSelectInsight: (insightId: string) => void;
};

export default function XrayPdfCanvas({
  currentPage,
  pdfUrl,
  zoom,
  selectedInsightId,
  visibleOverlays,
  onLoadError,
  onLoadSuccess,
  onSelectInsight,
}: XrayPdfCanvasProps) {
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const [pdfPageWidth, setPdfPageWidth] = useState(780);
  const [reactPdf, setReactPdf] = useState<ReactPdfModule | null>(null);

  useEffect(() => {
    let active = true;

    void (async () => {
      try {
        const reactPdfModule = await import("react-pdf");
        if (!isPdfWorkerConfigured) {
          reactPdfModule.pdfjs.GlobalWorkerOptions.workerSrc =
            `https://unpkg.com/pdfjs-dist@${reactPdfModule.pdfjs.version}/build/pdf.worker.min.mjs`;
          isPdfWorkerConfigured = true;
        }
        if (active) setReactPdf(reactPdfModule);
      } catch (err) {
        if (!active) return;
        onLoadError(err instanceof Error ? err.message : "Could not initialize PDF renderer");
      }
    })();

    return () => {
      active = false;
    };
  }, [onLoadError]);

  useEffect(() => {
    const node = viewportRef.current;
    if (!node) return;

    const updateWidth = () => {
      const maxByPane = Math.floor(node.clientWidth - 40);
      const nextWidth = Math.max(280, maxByPane);
      setPdfPageWidth(nextWidth * zoom);
    };

    updateWidth();
    const observer = new ResizeObserver(updateWidth);
    observer.observe(node);
    return () => observer.disconnect();
  }, [zoom]);

  if (!reactPdf) {
    return (
      <div className="xray-canvas" ref={viewportRef}>
        <p className="xray-canvas-note">Loading PDF viewer...</p>
      </div>
    );
  }

  const { Document, Page } = reactPdf;

  return (
    <div className="xray-canvas" ref={viewportRef}>
      <div className="xray-pdf-stage">
        <Document
          file={pdfUrl}
          loading={<p className="xray-canvas-note">Loading PDF...</p>}
          onLoadSuccess={({ numPages }) => onLoadSuccess(numPages)}
          onLoadError={(err) => onLoadError(err instanceof Error ? err.message : "Could not render PDF")}
        >
          <Page
            key={`${currentPage}-${pdfPageWidth}`}
            pageNumber={currentPage}
            width={pdfPageWidth}
            renderAnnotationLayer={false}
            renderTextLayer={false}
          />
        </Document>
        <div className="xray-canvas-grid" />
        <div className="xray-overlay-layer">
          {visibleOverlays.map((insight) => (
            <button
              key={insight.id}
              className={`overlay overlay-${insight.anomaly_flag.toLowerCase()} ${selectedInsightId === insight.id ? "active" : ""}`}
              style={{
                left: `${insight.bbox_x0 * 100}%`,
                top: `${insight.bbox_y0 * 100}%`,
                width: `${Math.max(0.6, (insight.bbox_x1 - insight.bbox_x0) * 100)}%`,
                height: `${Math.max(0.8, (insight.bbox_y1 - insight.bbox_y0) * 100)}%`,
              }}
              onClick={() => onSelectInsight(insight.id)}
              title={`${insight.clause_type} | Page ${insight.page_number}`}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
