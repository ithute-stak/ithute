import { BookOpen, Layers, Users, Award } from "lucide-react";
import React from "react";

interface CourseFeature {
    title: string;
    description: string;
    icon: React.ElementType;
}

export const courseFeatures: CourseFeature[] = [
    {
        title: "Comprehensive Courses",
        description:
            "Access a wide range of carefully curated courses designed by industry experts.",
        icon: BookOpen,
    },
    {
        title: "Structured Learning",
        description:
            "Follow well-organized learning paths to master skills step by step.",
        icon: Layers,
    },
    {
        title: "Community Support",
        description:
            "Engage with instructors and peers through discussions and groups.",
        icon: Users,
    },
    {
        title: "Certification",
        description:
            "Earn certificates to showcase your achievements and skills.",
        icon: Award,
    },
];