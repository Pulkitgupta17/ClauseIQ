import { useTheme } from "next-themes";
import type * as React from "react";
import { Toaster as SonnerToaster } from "sonner";

type ToasterProps = React.ComponentProps<typeof SonnerToaster>;

export function Toaster(props: ToasterProps) {
  const { theme = "dark" } = useTheme();
  return (
    <SonnerToaster
      theme={theme as ToasterProps["theme"]}
      richColors
      closeButton
      position="bottom-right"
      {...props}
    />
  );
}
