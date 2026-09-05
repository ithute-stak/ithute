import {Card, CardContent, CardHeader, CardTitle} from "@/components/ui/card";
import {Badge} from "@/components/ui/badge";
import {Separator} from "@/components/ui/separator";
import {UserCheck} from "lucide-react";
import {UserRole} from "@/types/shared.primitive";
import {useAppData} from "@/provider/dataProvider";

export function RecentStudents(){
    const {
        students,
    } = useAppData()
    const recentStudents = students.filter((q)=>q.user.role === UserRole.student).slice(0, 5)
    return <Card>
        <CardHeader>
            <CardTitle className="text-sm font-medium flex items-center gap-2">
                <UserCheck className="h-4 w-4" />
                Recent Students
            </CardTitle>
        </CardHeader>

        <CardContent className="space-y-3">
            {recentStudents.map((student) => (
                <div
                    key={student.id}
                    className="space-y-2"
                >
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-sm font-medium">
                                {
                                    student.user?.person
                                        ?.first_name
                                }{" "}
                                {
                                    student.user?.person
                                        ?.last_name
                                }
                            </p>

                            <p className="text-xs text-muted-foreground">
                                {
                                    student.admission_number
                                }
                            </p>
                        </div>

                        <Badge variant="outline">
                            {
                                student.user?.person
                                    ?.gender
                            }
                        </Badge>
                    </div>

                    <Separator />
                </div>
            ))}
        </CardContent>
    </Card>
}