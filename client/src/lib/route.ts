// Hash routes (arch §3 "Screens"). Hash routing keeps the app one static page under /app/.
export type Route =
  | { screen: "picker" }
  | { screen: "home" }
  | { screen: "session" }
  | { screen: "journey" }
  | { screen: "lesson"; skillId: string }
  | { screen: "library" }
  | { screen: "progress" }
  | { screen: "play"; id: string }
  | { screen: "parent"; page: string | null };

export function parse(hash: string): Route {
  const path = hash.replace(/^#\/?/, "");
  const [head, arg] = path.split("/");
  switch (head) {
    case "home": return { screen: "home" };
    case "session": return { screen: "session" };
    case "journey": return { screen: "journey" };
    case "library": return { screen: "library" };
    case "progress": return { screen: "progress" };
    case "lesson": if (arg) return { screen: "lesson", skillId: decodeURIComponent(arg) }; break;
    case "play": if (arg && /^[\w-]+$/.test(arg)) return { screen: "play", id: arg }; break;
    case "parent": return { screen: "parent", page: arg || null };
  }
  return { screen: "picker" };
}

export function go(path: string): void {
  location.hash = `#/${path}`;
}
