import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Ithute Digital Solutions",
    short_name: "IDS",
    description: "Ithute Digital Solutions control centre for hosted applications, business email, DNS and connected services.",
    start_url: "/dashboard",
    scope: "/",
    display: "standalone",
    background_color: "#f6f8fc",
    theme_color: "#0b315f",
    categories: ["business", "productivity", "utilities"],
    icons: [
      { src: "/brand/ids-mark.svg", sizes: "any", type: "image/svg+xml", purpose: "any" },
      { src: "/brand/ids-mark.svg", sizes: "any", type: "image/svg+xml", purpose: "maskable" },
    ],
  };
}
