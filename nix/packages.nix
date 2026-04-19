# nix/packages.nix — avoi Agent package built with uv2nix
{ inputs, ... }:
{
  perSystem =
    { pkgs, inputs', ... }:
    let
      avoiVenv = pkgs.callPackage ./python.nix {
        inherit (inputs) uv2nix pyproject-nix pyproject-build-systems;
      };

      avoiTui = pkgs.callPackage ./tui.nix {
        npm-lockfile-fix = inputs'.npm-lockfile-fix.packages.default;
      };

      # Import bundled skills, excluding runtime caches
      bundledSkills = pkgs.lib.cleanSourceWith {
        src = ../skills;
        filter = path: _type: !(pkgs.lib.hasInfix "/index-cache/" path);
      };

      avoiWeb = pkgs.callPackage ./web.nix {
        npm-lockfile-fix = inputs'.npm-lockfile-fix.packages.default;
      };

      runtimeDeps = with pkgs; [
        nodejs_22
        ripgrep
        git
        openssh
        ffmpeg
        tirith
      ];

      runtimePath = pkgs.lib.makeBinPath runtimeDeps;

      # Lockfile hashes for dev shell stamps
      pyprojectHash = builtins.hashString "sha256" (builtins.readFile ../pyproject.toml);
      uvLockHash =
        if builtins.pathExists ../uv.lock then
          builtins.hashString "sha256" (builtins.readFile ../uv.lock)
        else
          "none";
    in
    {
      packages = {
        default = pkgs.stdenv.mkDerivation {
          pname = "avoi-agent";
          version = (fromTOML (builtins.readFile ../pyproject.toml)).project.version;

          dontUnpack = true;
          dontBuild = true;
          nativeBuildInputs = [ pkgs.makeWrapper ];

          installPhase = ''
            runHook preInstall

            mkdir -p $out/share/avoi-agent $out/bin
            cp -r ${bundledSkills} $out/share/avoi-agent/skills
            cp -r ${avoiWeb} $out/share/avoi-agent/web_dist

            # copy pre-built TUI (same layout as dev: ui-tui/dist/ + node_modules/)
            mkdir -p $out/ui-tui
            cp -r ${avoiTui}/lib/avoi-tui/* $out/ui-tui/

            ${pkgs.lib.concatMapStringsSep "\n"
              (name: ''
                makeWrapper ${avoiVenv}/bin/${name} $out/bin/${name} \
                  --suffix PATH : "${runtimePath}" \
                  --set avoi_BUNDLED_SKILLS $out/share/avoi-agent/skills \
                  --set avoi_WEB_DIST $out/share/avoi-agent/web_dist \
                  --set avoi_TUI_DIR $out/ui-tui \
                  --set avoi_PYTHON ${avoiVenv}/bin/python3 \
                  --set avoi_NODE ${pkgs.nodejs_22}/bin/node
              '')
              [
                "avoi"
                "avoi-agent"
                "avoi-acp"
              ]
            }

            runHook postInstall
          '';

          passthru.devShellHook = ''
            STAMP=".nix-stamps/avoi-agent"
            STAMP_VALUE="${pyprojectHash}:${uvLockHash}"
            if [ ! -f "$STAMP" ] || [ "$(cat "$STAMP")" != "$STAMP_VALUE" ]; then
              echo "avoi-agent: installing Python dependencies..."
              uv venv .venv --python ${pkgs.python312}/bin/python3 2>/dev/null || true
              source .venv/bin/activate
              uv pip install -e ".[all]"
              [ -d mini-swe-agent ] && uv pip install -e ./mini-swe-agent 2>/dev/null || true
              [ -d tinker-atropos ] && uv pip install -e ./tinker-atropos 2>/dev/null || true
              mkdir -p .nix-stamps
              echo "$STAMP_VALUE" > "$STAMP"
            else
              source .venv/bin/activate
              export avoi_PYTHON=${avoiVenv}/bin/python3
            fi
          '';

          meta = with pkgs.lib; {
            description = "AI agent with advanced tool-calling capabilities";
            homepage = "https://github.com/AVOI/avoi-agent";
            mainProgram = "avoi";
            license = licenses.mit;
            platforms = platforms.unix;
          };
        };

        tui = avoiTui;
        web = avoiWeb;
      };
    };
}
