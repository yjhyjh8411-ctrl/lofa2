{ pkgs, ... }: {
  channel = "stable-23.11";

  packages = [
    pkgs.python3
    pkgs.python3Packages.pip
    pkgs.stdenv.cc.cc.lib
    pkgs.nodejs_20
  ];

  env = {
    LD_LIBRARY_PATH = "${pkgs.stdenv.cc.cc.lib}/lib";
  };

  idx = {
    extensions = [
      "ms-python.python"
    ];

    workspace = {
      onCreate = {
        install = ''
          cd functions
          python3 -m venv venv
          source venv/bin/activate
          pip install -r requirements.txt
        '';
      };
      onStart = {};
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
            HOST = "0.0.0.0";
          };
        };
      };
    };
  };
}
