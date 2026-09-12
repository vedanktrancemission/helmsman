import { Component, ReactNode, Suspense, lazy } from "react";

/** three.js is heavy — it must stay out of the main bundle. */
const HelmHero = lazy(() => import("./HelmHero"));

/** One-time probe: plenty of machines, VMs and locked-down browsers have no
 *  WebGL at all, and asking twice costs a second throwaway context. */
let supported: boolean | null = null;
function webglSupported(): boolean {
  if (supported !== null) return supported;
  try {
    const probe = document.createElement("canvas");
    const gl = probe.getContext("webgl2") || probe.getContext("webgl");
    supported = !!gl;
    // Release the probe's context rather than leaving it to the GC.
    (gl as WebGLRenderingContext | null)?.getExtension("WEBGL_lose_context")?.loseContext();
  } catch {
    supported = false;
  }
  return supported;
}

/** The hero is pure decoration. If the GPU path fails for any reason, the
 *  Builder still has to render — so swallow the error and show nothing. */
class HeroBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    return this.state.failed ? null : this.props.children;
  }
}

export default function CanvasHero() {
  if (!webglSupported()) return null;
  return (
    <HeroBoundary>
      <Suspense fallback={null}>
        <HelmHero />
      </Suspense>
    </HeroBoundary>
  );
}
