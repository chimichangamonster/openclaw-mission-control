declare module "leaflet.heat" {
  import * as L from "leaflet";
  // Side-effect import — adds L.heatLayer to leaflet namespace
}

declare namespace L {
  function heatLayer(
    latlngs: [number, number, number][],
    options?: {
      minOpacity?: number;
      maxZoom?: number;
      max?: number;
      radius?: number;
      blur?: number;
      gradient?: Record<number, string>;
    },
  ): L.Layer;
}
