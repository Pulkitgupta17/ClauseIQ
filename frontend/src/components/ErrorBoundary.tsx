import { Button } from "@/components/ui/button";
import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/** Catches render errors and shows a recoverable fallback. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Unhandled UI error", error, info.componentStack);
  }

  render(): ReactNode {
    if (this.state.error) {
      return (
        <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-6 text-center">
          <h2 className="font-semibold text-xl">Something went wrong</h2>
          <p className="max-w-md text-muted-foreground text-sm">{this.state.error.message}</p>
          <Button
            onClick={() => {
              this.setState({ error: null });
              window.location.reload();
            }}
          >
            Reload
          </Button>
        </div>
      );
    }
    return this.props.children;
  }
}
