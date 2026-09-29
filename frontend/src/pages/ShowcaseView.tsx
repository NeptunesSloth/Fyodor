import { useEffect, useRef } from "react";
import { plane, type PlaneId } from "../theme/planes";
import { Showcase } from "../table3d/Showcase";

export default function ShowcaseView({ planeId }: { planeId: PlaneId }) {
  const host = useRef<HTMLDivElement>(null);
  const scene = useRef<Showcase | null>(null);
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const s = new Showcase(el, plane(planeId));
    scene.current = s;
    const ro = new ResizeObserver(() => s.resize(el.clientWidth, el.clientHeight));
    ro.observe(el);
    s.resize(el.clientWidth, el.clientHeight);
    return () => {
      ro.disconnect();
      s.dispose();
      scene.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => scene.current?.setPlane(plane(planeId)), [planeId]);
  return <div className="home-showcase" ref={host} aria-hidden />;
}
