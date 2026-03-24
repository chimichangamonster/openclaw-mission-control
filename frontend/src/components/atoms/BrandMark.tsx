import Image from "next/image";

export function BrandMark() {
  return (
    <div className="flex items-center gap-3">
      <Image
        src="/logo.png"
        alt="VantageClaw"
        width={40}
        height={40}
        className="rounded-lg shadow-sm"
      />
      <div className="leading-tight">
        <div className="font-heading text-sm uppercase tracking-[0.26em] text-strong">
          VANTAGECLAW
        </div>
        <div className="text-[11px] font-medium text-quiet">
          Mission Control
        </div>
      </div>
    </div>
  );
}
