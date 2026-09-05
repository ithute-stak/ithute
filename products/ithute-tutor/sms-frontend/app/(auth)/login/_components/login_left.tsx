import Image from "next/image";
export const LoginLeftSide = ()=>{
    return <div className="hidden md:flex flex-col justify-center items-center relative overflow-hidden">

        {/* background glow */}
        <div className="absolute w-125 h-125 bg-linear-to-br from-slate-50 via-white to-slate-100 blur-3xl rounded-full top-20 left-20" />
        <div className="absolute w-100 h-100 bg-linear-to-br from-slate-50 via-white to-slate-100 blur-3xl rounded-full bottom-20 right-20" />

        <div className="z-10 flex flex-col items-center text-center px-10">

            <div className="bg-white shadow-xl rounded-full p-4 mb-6">
                <Image
                    src="/logo.png"
                    alt="School System"
                    width={96}
                    height={96}
                    className="rounded-full object-cover"
                />
            </div>

            <h1 className="text-4xl font-bold tracking-tight text-gray-900">
                Smart School Management
            </h1>

            <p className="text-gray-500 mt-4 max-w-md leading-relaxed">
                Manage students, teachers, parents, and academic operations in one
                powerful unified system built for modern education.
            </p>

            <div className="mt-8 flex gap-3 text-sm text-gray-500">
                <span className="px-3 py-1 bg-white shadow rounded-full">Secure</span>
                <span className="px-3 py-1 bg-white shadow rounded-full">Fast</span>
                <span className="px-3 py-1 bg-white shadow rounded-full">Multi-school</span>
            </div>

        </div>
    </div>
}