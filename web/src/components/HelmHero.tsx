import { useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import type { Group } from "three";

const ACCENT = "#f5a623";
const BLUE = "#4aa3ff";
const SPOKES = 8;

/** Honoured at mount — the scene is only ever shown on an empty canvas, so it
 *  does not need to react to the setting changing mid-session. */
const STILL =
  typeof window !== "undefined" &&
  window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** A ship's wheel: rim, hub, eight spokes, and the handles past the rim. */
function Helm() {
  const group = useRef<Group>(null);

  useFrame((state, delta) => {
    const g = group.current;
    if (!g || STILL) return;
    g.rotation.z -= delta * 0.11;
    // A slow figure-eight tilt, so the form reads as solid rather than flat.
    g.rotation.x = Math.sin(state.clock.elapsedTime * 0.25) * 0.13;
    g.rotation.y = Math.cos(state.clock.elapsedTime * 0.19) * 0.15;
  });

  const angles = Array.from({ length: SPOKES }, (_, i) => (i / SPOKES) * Math.PI * 2);

  return (
    <group ref={group} rotation={[0.2, -0.25, 0]} position={[0, 0.7, 0]}>
      <mesh>
        <torusGeometry args={[1.6, 0.075, 16, 96]} />
        <meshStandardMaterial
          color={ACCENT} emissive={ACCENT} emissiveIntensity={0.28}
          roughness={0.38} metalness={0.5}
        />
      </mesh>

      <mesh>
        <torusGeometry args={[0.34, 0.07, 16, 48]} />
        <meshStandardMaterial
          color={BLUE} emissive={BLUE} emissiveIntensity={0.32}
          roughness={0.38} metalness={0.5}
        />
      </mesh>

      {angles.map((a, i) => (
        <group key={i} rotation={[0, 0, a]}>
          <mesh position={[0, 0.97, 0]}>
            <cylinderGeometry args={[0.045, 0.045, 1.32, 12]} />
            <meshStandardMaterial
              color={ACCENT} emissive={ACCENT} emissiveIntensity={0.18}
              roughness={0.45} metalness={0.45}
            />
          </mesh>
          <mesh position={[0, 1.96, 0]}>
            <cylinderGeometry args={[0.058, 0.042, 0.58, 12]} />
            <meshStandardMaterial
              color={ACCENT} emissive={ACCENT} emissiveIntensity={0.26}
              roughness={0.45} metalness={0.45}
            />
          </mesh>
        </group>
      ))}
    </group>
  );
}

export default function HelmHero() {
  return (
    <Canvas
      camera={{ position: [0, 0, 13.2], fov: 42 }}
      dpr={[1, 2]}
      gl={{ alpha: true, antialias: true }}
      // The canvas must never swallow pan / zoom meant for React Flow beneath it.
      style={{ pointerEvents: "none", background: "transparent" }}
    >
      <ambientLight intensity={0.55} />
      <directionalLight position={[4, 5, 6]} intensity={2.4} color="#ffd9a0" />
      <directionalLight position={[-6, -3, 2]} intensity={1.3} color={BLUE} />
      <Helm />
    </Canvas>
  );
}
