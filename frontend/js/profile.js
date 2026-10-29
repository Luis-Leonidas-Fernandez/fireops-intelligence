(() => {
  "use strict";

  function initialsFor(value) {
    const words = value.trim().match(/[\p{L}\p{N}]+/gu) || [];
    if (words.length > 1) return `${words[0][0]}${words.at(-1)[0]}`.toUpperCase();
    return (words[0] || "").slice(0, 2).toUpperCase();
  }

  async function mount() {
    const nameNode = document.querySelector("#profile-name");
    const emailNode = document.querySelector("#profile-email");
    const avatarNode = document.querySelector("#profile-avatar");
    const roleNode = document.querySelector("#profile-role");
    if (!nameNode || !emailNode || !avatarNode) return;

    try {
      const response = await fetch("/auth/me", { credentials: "same-origin" });
      if (response.status === 401) {
        const pathname = window.location.pathname || "";
        const search = window.location.search || "";
        const current = pathname + search;
        const target = current && current !== "/" ? `?next=${encodeURIComponent(current)}` : "";
        window.location.assign(`/iniciar-sesion${target}`);
        return;
      }
      if (!response.ok) throw new Error("Profile unavailable");
      const user = await response.json();
      if (typeof user.email !== "string" || !user.email) throw new Error("Invalid profile");
      const name = typeof user.display_name === "string" && user.display_name.trim()
        ? user.display_name.trim() : user.email;
      nameNode.textContent = name;
      emailNode.textContent = user.email;
      avatarNode.textContent = initialsFor(name === user.email ? user.email.split("@")[0] : name);

      if (roleNode) {
        if (user.role) {
          roleNode.textContent = user.role;
          roleNode.hidden = false;
          roleNode.dataset.role = user.role;
          roleNode.setAttribute("aria-label", `Rol operativo: ${user.role}`);
        } else {
          roleNode.hidden = true;
          roleNode.textContent = "";
        }
      }

      // Propagate role to Navigation Controller if available
      if (window.FireNavigationController && typeof window.FireNavigationController.setRole === "function") {
        window.FireNavigationController.setRole(user.role || null);
      } else if (window.FireNavigation && typeof window.FireNavigation.createNavigationController === "function") {
        window.FireNavigationController = window.FireNavigation.createNavigationController({ initialRole: user.role || null });
      }

      if (typeof document.querySelectorAll === "function") {
        const isAdmin = user.role === "ADMINISTRADOR";
        document.querySelectorAll('[data-view="Invitaciones"]').forEach((btn) => {
          btn.hidden = !isAdmin;
        });
      }

      return user;
    } catch (_error) {
      nameNode.textContent = "Cuenta";
      emailNode.textContent = "";
      avatarNode.textContent = "··";
      if (roleNode) {
        roleNode.hidden = true;
        roleNode.textContent = "";
      }
      return null;
    }
  }

  window.DashboardProfile = Object.freeze({ mount });
})();
