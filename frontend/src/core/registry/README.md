# `core/registry/`

The module registry. Adding a module is a folder plus one line here.

```ts
interface ModuleDefinition {
  id: string;
  label: string;
  icon: LucideIcon;
  navItems: NavItem[];
  routes: RouteDefinition[];
}
```

A static array, not auto-discovery: explicit registration means the nav order is
readable in one place and a module cannot appear by accident.

V1 registers exactly one module — Video Composer. Dashboard, Lead Finder, CRM,
Outreach, Analytics, and AI Assistant each become one more entry.
