export function NavigationBar() {
  return (
    <nav className="flex gap-2 justify-center">
      <a
        href="http://localhost:5174"
        className="px-4 py-1.5 rounded-full text-sm font-medium bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors"
      >
        Game Dashboard
      </a>
      <a
        href="http://localhost:5173"
        className="px-4 py-1.5 rounded-full text-sm font-medium bg-blue-600 text-white"
      >
        Agent Config
      </a>
    </nav>
  )
}
