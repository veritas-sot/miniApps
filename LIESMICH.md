# veritas nautobot miniApps

# Table of contents
1. [Übersicht](#*introduction*)
2. [Installation](#installation)
    1. [Python Environment](#install_python_env)
    2. [Installation der Library](#install_python_lib)
3. [Grundkonfiguration](#miniapps_configs)
4. [Profile](#profiles)
5. [onboarding](#onboarding)
6. [kobold](#kobold)
7. [nachtwaechter](#nachtwaechter)
8. [scan_prefixes](#scan_prefixes)
9. [set_latency](#set_latency)
10. [set_link](#set_link)
11. [set_snmp](#set_snmp)
12. [sync_cmk](#sync_cmk)
13. [sync_smokeping](#sync_smokeping)
14. [sync_phpipam](#sync_phpipam)
15. [updater](#updater)
16. [authentication](#authentication)


# Übersicht <a name="introduction"></a>

Die veritas MiniApps helfen Netzwerkern:

* Geräte zu Nautobot hinzuzufügen
* Gerätedaten zu modifizieren (Massenupdate, Trnsformstion von Werten etc.)
* Custom Fields wie latency, snmp_credentials zu setzen
* CheckMK, Smokeping und phpIPAM zu konfigurieren, so dass diese immer die aktuelle Konfiguration haben
* IP-Adressen zu scannen und in nautobot zu aktualisieren bzw. hinzuzufügen

# Installation <a name="installation"></a>

Die Installtion ist recht einfach. veritas nutzt poetry, um Abhängigkeiten aufzulösen. 

## Python Environment <a name="install_python_env"></a>

Es ist am einfachsten, ein lokales Python-Environment zu nutzen. So kann man zum Beispiel (mini)conda nutzen.

Mit

```
conda create --name veritas python=3.11
```

wird ein neues Environment mit dem Namen 'veritas' und der Python Version 3.11 angelegt.

## Installation der Library <a name="install_python_lib"></a>

Mit 

```
poetry install
```

wird die Library installiert und kann anschließend genutzt werden.

# Grundkonfiguration der MiniApps <a name="miniapps_configs"></a>

Jede MiniApp wird durch eine YAML-Konfiguration konfiguriert. veritas nutzt dabei folgende Prioritäten

1. ~/.veritas/miniapps/__appname__/__appname__.yaml
2. lokales miniApp Verzeichnis z.B. miniApps/onvoarding/onboarding.yaml
3. ./conf Unterverzeichnis der MiniApp z.B. miniApps/onboarsing/conf/onboarding.yaml
4. /etc/veritas/miniapps/__appname__/__appname__.yaml

Einige MiniApps benötigen ein Profil (Benutzername und Passwort) um sich bei einem Netzwerkgerät einzuloggen. Dieses Profile wird in der Datei profile.yaml gespeichert. Dabei gilt die gleiche Prioriätenliste wie für die Apps. 

# Profile <a name="profiles"></a>

Die MiniApps onboarding, kobold, der nachtwaechter sowie die ./script_bakery benötigen ein Profil. Eine profiles.yaml hat folgenden Aufbau:

```
---
profiles:
  default:
      # username to login to devices
      username: "__USERNAME__"
      # encrypted and base64 encoded password
      password: "__PASSWORD__"
```

Der Username ist der bekannte Login, um sich bei einem Gerät anzumelden. Dass Passwort wird verschlüsselt abgelegt. Es kann mit Hilfe der MiniApp ./encrypt_password.py erstellt werden. 

```
./encrypt_password.py

Enter password:

b'Z0FBQUFBQmxtWjBrV1pQZmxybnhuNmZOTGlYZHBQb0JyOU9Vajdrb0ZKek5rYi1iY1BpSVdTanMtNEdaQlNqNFJzY2dFcXY4ZHE0UUVzSWxfN3hwWnJCc2RNd0lzMkxoOHc9PQ=='
```

Dabei muss darauf geachtet werden, dass die Parameter in der Datei .env passend gesetzt sind. **Diese Parameter werden sowohl beim entschlüsseln wie auch beim entschlüsseln genutzt und müssen daher übereinstimmen.**
Das angezeigte Passwort **zwischen** dem Hochkomme, also '...', kann in der profiles.yaml anschließend genutzt werden.

Die drei Parameter 

* ENCRYPTIONKEY
* SALT
* ITERATIONS

können entweder in einer local .env Datei (wird bei jeder MiniApp benötigt, die ein Profil nutzt!) konfiguriert werden. Wichtig dabei ist die Schreibweise. Alle Parameter müssen in der .env-Datei **GROSS** geschrieben werden. Alternativ kann im MiniApp-Konfigurationsverzeichnis eine Datei salt.yaml abgelegt werden. Diese muss wie folgt aussehen:

```
---
crypto:
  encryptionkey: lab
  salt: mysecretsalt
  iterations: 390000
```

In der salt.yaml Datei werden die Parameter dagegen kleingeschrieben.

# Onboarding <a name="Onboarding"></a>

Mit Hilfe der onboarding-App können Geräte vollautomatisiert zu nautobot hinzugefügt werden:

Um die Konfigurationen aller Geräte einer Excel-Datei zu exportieren:

```
./onboarding.py --profile default --loglevel info --inventory inventory.xlsx --export
```

Alle Konfigurationen und Facts werden im Verzeichnis ./export gespeichert. Dies erleichtert den Import, falls dieser mehrfach angepasst werden soll.

Möchte man alle Geräte, deren Konfiguration vorher exportiert wurdn, importieren und 'nur' das Primäre-Interface hinzufügen, kann dies wie folgt gemacht werden:

```
./onboarding.py --profile default --loglevel info --inventory inventory.xlsx --import --onboarding --primary-only
```

Möchte man alle Interface hinzufügen, wird statt --primary-only -- interfaces genutzt. 

```
./onboarding.py --profile default --loglevel info --inventory inventory.xlsx --import --onboarding --iterfaces
```

