import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useAnalyzeContract } from "@/hooks/useAnalyzeContract";
import { MAX_PDF_BYTES, extractPdfText } from "@/lib/pdf";
import { SAMPLE_CONTRACT } from "@/lib/sample";
import { type AnalysisRequest, analysisRequestSchema, jurisdictions } from "@/lib/schemas";
import { cn } from "@/lib/utils";
import { zodResolver } from "@hookform/resolvers/zod";
import { motion } from "framer-motion";
import { FileText, Loader2, Sparkles, Upload } from "lucide-react";
import { useState } from "react";
import { useDropzone } from "react-dropzone";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

export function ContractUploader() {
  const analyze = useAnalyzeContract();
  const [extracting, setExtracting] = useState(false);

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors },
  } = useForm<AnalysisRequest>({
    resolver: zodResolver(analysisRequestSchema),
    defaultValues: { contract_text: "", jurisdiction: "IN-MH" },
  });

  const contractText = watch("contract_text") ?? "";

  async function handleFiles(files: File[]) {
    const file = files[0];
    if (!file) {
      return;
    }
    if (file.size > MAX_PDF_BYTES) {
      toast.error("That PDF is larger than 5 MB.");
      return;
    }
    setExtracting(true);
    try {
      const text = await extractPdfText(file);
      if (text.length < 100) {
        toast.error(
          "Couldn't extract enough text (is it a scanned image?). Paste the text instead.",
        );
        return;
      }
      setValue("contract_text", text, { shouldValidate: true });
      toast.success(`Read ${text.length.toLocaleString()} characters from ${file.name}.`);
    } catch {
      toast.error("Could not read that PDF. Try pasting the text instead.");
    } finally {
      setExtracting(false);
    }
  }

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop: handleFiles,
    accept: { "application/pdf": [".pdf"] },
    maxFiles: 1,
    maxSize: MAX_PDF_BYTES,
    disabled: extracting,
  });

  return (
    <form
      onSubmit={handleSubmit((values) => analyze.mutate(values))}
      className="space-y-4"
      aria-label="Contract analysis form"
    >
      <div
        {...getRootProps()}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-border border-dashed px-6 py-10 text-center transition-colors",
          isDragActive && "border-primary bg-primary/5",
          extracting && "pointer-events-none opacity-70",
        )}
      >
        <input {...getInputProps()} aria-label="Upload a PDF contract" />
        <motion.div
          animate={isDragActive ? { scale: 1.1, y: -4 } : { scale: 1, y: 0 }}
          className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-muted"
        >
          {extracting ? (
            <Loader2 className="h-5 w-5 animate-spin" />
          ) : isDragActive ? (
            <FileText className="h-5 w-5 text-primary" />
          ) : (
            <Upload className="h-5 w-5 text-muted-foreground" />
          )}
        </motion.div>
        <p className="font-medium text-sm">
          {extracting
            ? "Reading PDF…"
            : isDragActive
              ? "Drop the PDF here"
              : "Drop a PDF or click to upload"}
        </p>
        <p className="mt-1 text-muted-foreground text-xs">
          PDF only · max 5 MB · text extracted in your browser
        </p>
      </div>

      <div className="space-y-1.5">
        <Textarea
          {...register("contract_text")}
          rows={6}
          placeholder="…or paste contract text here"
          aria-invalid={Boolean(errors.contract_text)}
        />
        <div className="flex items-center justify-between text-xs">
          <span className="text-destructive">{errors.contract_text?.message ?? ""}</span>
          <span className="text-muted-foreground tabular-nums">{contractText.length} chars</span>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <select
          {...register("jurisdiction")}
          aria-label="Jurisdiction"
          className="h-9 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {jurisdictions.map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => setValue("contract_text", SAMPLE_CONTRACT, { shouldValidate: true })}
        >
          <Sparkles className="h-4 w-4" />
          Try sample contract
        </Button>
        <Button type="submit" className="ml-auto" disabled={analyze.isPending || extracting}>
          {analyze.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          Analyse contract
        </Button>
      </div>
    </form>
  );
}
