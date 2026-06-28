/** Maximum accepted PDF size (5 MB), in bytes. */
export const MAX_PDF_BYTES = 5 * 1024 * 1024;

/**
 * Extract text from a PDF entirely in the browser (pdfjs is lazy-imported so it
 * stays out of the initial bundle). The backend's analyze endpoint takes text,
 * so extraction happens client-side here.
 */
export async function extractPdfText(file: File): Promise<string> {
  const pdfjs = await import("pdfjs-dist");
  pdfjs.GlobalWorkerOptions.workerSrc = new URL(
    "pdfjs-dist/build/pdf.worker.min.mjs",
    import.meta.url,
  ).toString();

  const data = await file.arrayBuffer();
  const document = await pdfjs.getDocument({ data }).promise;
  const pages: string[] = [];
  for (let pageNumber = 1; pageNumber <= document.numPages; pageNumber += 1) {
    const page = await document.getPage(pageNumber);
    const content = await page.getTextContent();
    const text = content.items.map((item) => ("str" in item ? item.str : "")).join(" ");
    pages.push(text);
  }
  return pages
    .join("\n")
    .replace(/[ \t]+/g, " ")
    .trim();
}
