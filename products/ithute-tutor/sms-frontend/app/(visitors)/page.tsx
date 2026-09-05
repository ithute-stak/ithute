import { Badge } from "@/components/ui/badge";
import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { courseFeatures } from "@/components/course_features";
import {
    Card,
    CardContent,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";

export default function Home() {
    return (
        <div className="flex flex-col gap-24 py-10">

            {/* 🔥 Hero Section */}
            <section className="relative flex flex-col items-center text-center space-y-8 px-4">

                <Badge variant="outline" className="rounded-full px-4 py-1">
                    The Future of Online Education
                </Badge>

                <h1 className="text-4xl md:text-6xl lg:text-7xl font-bold tracking-tight max-w-4xl">
                    Elevate your Learning Experience with{" "}
                    <span className="text-primary">Ithute Solutions</span>
                </h1>

                <p className="max-w-2xl text-muted-foreground md:text-lg lg:text-xl">
                    Discover a new way to learn with our modern, interactive
                    learning management system. Access high-quality courses anytime,
                    anywhere.
                </p>

                <div className="flex flex-col sm:flex-row gap-4 mt-6">
                    <Link
                        className={buttonVariants({ size: "lg" })}
                        href="/courses"
                    >
                        Explore Courses
                    </Link>

                    <Link
                        href="/login"
                        className={`${buttonVariants({
                            size: "lg",
                            variant: "outline",
                        })} border border-border bg-background hover:bg-primary hover:text-primary-foreground transition`}
                    >
                        Get Started
                    </Link>
                </div>
            </section>

            {/* 🔥 Features Section */}
            <section className="px-4">
                <div className="max-w-6xl mx-auto">

                    {/* Section Title */}
                    <div className="text-center mb-12 space-y-3">
                        <h2 className="text-2xl md:text-3xl font-semibold">
                            Powerful Features for Modern Learning
                        </h2>
                        <p className="text-muted-foreground max-w-xl mx-auto">
                            Everything you need to manage, teach, and learn in one platform.
                        </p>
                    </div>

                    {/* Grid */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
                        {courseFeatures.map((feature, index) => {
                            const Icon = feature.icon;

                            return (
                                <Card
                                    key={index}
                                    className="group hover:shadow-xl transition-all duration-300 border border-border bg-card hover:-translate-y-1"
                                >
                                    <CardHeader className="space-y-3">

                                        <div className="p-3 bg-primary/10 rounded-xl w-fit group-hover:bg-primary/20 transition">
                                            <Icon className="w-6 h-6 text-primary" />
                                        </div>

                                        <CardTitle className="text-lg">
                                            {feature.title}
                                        </CardTitle>
                                    </CardHeader>

                                    <CardContent>
                                        <p className="text-muted-foreground text-sm leading-relaxed">
                                            {feature.description}
                                        </p>
                                    </CardContent>
                                </Card>
                            );
                        })}
                    </div>
                </div>
            </section>

        </div>
    );
}