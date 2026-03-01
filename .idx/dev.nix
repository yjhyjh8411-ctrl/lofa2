{ pkgs, ... }: {
  channel = "stable-24.05";

  packages = [
    pkgs.python311
    pkgs.python311Packages.pip
    pkgs.python311Packages.virtualenv
    pkgs.nodejs_20
  ];

  env = {};

  idx = {
    extensions = [
      "ms-python.python"
    ];

    workspace = {
      onCreate = {
        install = ''
          cd functions
          python3.11 -m venv venv
          source venv/bin/activate
          pip install -r requirements.txt
        '';
      };
      onStart = {
        start = ''
          cd functions
          source venv/bin/activate
          python app.py &
        '';
      };
    };

    previews = {
      enable = true;
      previews = {
        web = {
          command = [
            "bash" "-c" "cd functions && source venv/bin/activate && python app.py"
          ];
          manager = "web";
          env = {
            PORT = "$PORT";
          };
        };
      };
    };
  };
}
