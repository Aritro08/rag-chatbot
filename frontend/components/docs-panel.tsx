import { useRef, type ChangeEvent } from "react";
import type { DocumentInfo } from "@/lib/types";
import { formatRelativeDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { FilePlus2, Trash2 } from "lucide-react";

interface DocsPanelProps {
  docs: DocumentInfo[];
  isLoading: boolean;
  isUploading: boolean;
  deletingFileId: number | null;
  onUploadFile: (file: File) => void;
  onDeleteFile: (fileId: number) => void;
}

export function DocsPanel({
  docs,
  isLoading,
  isUploading,
  deletingFileId,
  onUploadFile,
  onDeleteFile,
}: DocsPanelProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    onUploadFile(file);
    event.target.value = "";
  };

  return (
    <Card className="flex h-[80vh] min-h-[24rem] flex-col">
      <CardHeader className="space-y-3 border-b">
        <CardTitle className="text-base">Documents</CardTitle>
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          accept=".pdf,.docx,.html"
          onChange={handleFileChange}
        />
        <Button
          variant="secondary"
          className="w-full gap-2"
          onClick={() => fileInputRef.current?.click()}
          disabled={isUploading}
        >
          <FilePlus2 className="h-4 w-4" />
          {isUploading ? "Uploading..." : "Upload Document"}
        </Button>
      </CardHeader>
      <CardContent className="min-h-0 flex-1 overflow-y-auto p-2">
        {isLoading ? (
          <div className="space-y-2 p-2">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : docs.length ? (
          <ul className="space-y-1">
            {docs.map((doc) => (
              <li key={doc.id} className="rounded-lg border bg-muted/20 p-3 text-sm">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate font-medium">{doc.file_name}</p>
                    <p className="text-xs text-muted-foreground">{formatRelativeDate(doc.upload_timestamp)}</p>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 shrink-0 text-muted-foreground hover:text-destructive"
                    disabled={deletingFileId === doc.id}
                    onClick={() => onDeleteFile(doc.id)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="px-2 py-4 text-sm text-muted-foreground">No documents uploaded yet.</p>
        )}
      </CardContent>
    </Card>
  );
}
