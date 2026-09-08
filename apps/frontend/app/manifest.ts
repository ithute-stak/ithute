import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Ithute iMail",
    short_name: "iMail",
    description: "Ithute business mail workspace for hosted and connected accounts.",
    start_url: "/webmail/unified",
    scope: "/",
    display: "standalone",
    background_color: "#f6f8fc",
    theme_color: "#ffffff",
    categories: ["business", "productivity", "utilities"],
  };
}
