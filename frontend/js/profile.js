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
    if (!nameNode || !emailNode || !avatarNode) return;

    try {
      const response = await fetch("/auth/me", { credentials: "same-origin" });
      if (response.status === 401) {
        window.location.assign("/iniciar-sesion");
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
    } catch (_error) {
      nameNode.textContent = "Cuenta";
      emailNode.textContent = "";
      avatarNode.textContent = "··";
    }
  }

  window.DashboardProfile = Object.freeze({ mount });
})();
