# veritas nautobot miniApps

# Table of contents
1. [Übersicht](#*introduction*)
2. [Installation](#installation)
    1. [Python Environment](#install_python_env)
    2. [Installation der Library](#install_python_lib)
3. [Grundkonfiguration](#miniapps_configs)
    1. [Profile](#profiles)
    2. [Zugriff auf nautobot](#sot_config)
    3. [Restliche Konfiguration](#miniapp_config)
4. [onboarding](#onboarding)
    1. [Konfiguration](#onboarding_config)
    2. [Typischer Ablauf einer Migration](#migration)
5. [kobold](#kobold)
6. [nachtwaechter](#nachtwaechter)
7. [scan_prefixes](#scan_prefixes)
8. [set_latency](#set_latency)
9. [set_link](#set_link)
10. [set_snmp](#set_snmp)
11. [sync_cmk](#sync_cmk)
12. [sync_smokeping](#sync_smokeping)
13. [sync_phpipam](#sync_phpipam)
14. [updater](#updater)
15. [authentication](#authentication)


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

wird ein neues Environment mit dem Namen 'veritas' und der Python Version 3.11 angelegt. Poetry wird benötigt, um die Library zu installieren. Mit

```
conda install poetry
```

kann poetry installiert werden.

## Installation der Library <a name="install_python_lib"></a>

Mit 

```
poetry install
```

wird die Library installiert und kann anschließend genutzt werden.

# Grundkonfiguration der MiniApps <a name="miniapps_configs"></a>

Jede MiniApp wird durch eine YAML-Konfiguration konfiguriert. veritas nutzt dabei folgende Prioritäten um die Konfiguration zu lesen:

1. ~/.veritas/miniapps/__appname__/__appname__.yaml
2. lokales miniApp Verzeichnis z.B. miniApps/onvoarding/onboarding.yaml
3. ./conf Unterverzeichnis der MiniApp z.B. miniApps/onboarsing/conf/onboarding.yaml
4. /etc/veritas/miniapps/__appname__/__appname__.yaml

Einige MiniApps benötigen zudem ein Profil (Benutzername und Passwort) um sich bei einem Netzwerkgerät anzumelden. Dieses Profile wird in der Datei profile.yaml gespeichert. Dabei gilt die gleiche Prioriätenliste wie für die Apps. 

## Profile <a name="profiles"></a>

Die MiniApps onboarding, kobold, der nachtwaechter sowie die ./script_bakery benötigen ein Profil. Die Datei profiles.yaml hat folgenden Aufbau:

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

können entweder in einer local .env Datei (wird bei jeder MiniApp benötigt, die ein Profil benötigt!) konfiguriert werden. 

> Wichtig dabei ist die Schreibweise. Alle Parameter müssen in der .env-Datei **GROSS** geschrieben werden. Alternativ kann im MiniApp-Konfigurationsverzeichnis eine Datei salt.yaml abgelegt werden. 

Diese muss wie folgt aussehen:

```
---
crypto:
  encryptionkey: lab
  salt: mysecretsalt
  iterations: 390000
```

In der salt.yaml Datei werden die Parameter dagegen kleingeschrieben.

## Zugriff auf nautobot <a name="sot_config"></a>

Der Zugriff auf nautobot muss in der jeweiligen MiniApp Konfiguration konfiguriert werden Der Syntax lautet:

```
sot:
  nautobot: "__NAUTOBOT__"
  token: "__TOKEN__"
  ssl_verify: false
```

Durch den Parameter **nautobot** wird die URL festgelegt, also beispielsweise https://my-nautobot.meine-firma.de/. Token ist der in nautobot konfigurierte Token zur authentifizierung. 

> Wird ein privates TLS-Zertifikat genutzt und kann dies nicht verifiziert werden, so kann die Verifizierung durch den Parameter ssl_verify: false ausgeschaltetet werden. 

## Restliche konfiguration <a name="miniapp_config"></a>

Es gibt zahlreiche andere Parameter, die im Vorfeld noch konfiguriert werden müssen. Diese sind aber abhängig von der MiniApp. Alle Konfigurationen können in der dazugehörigen YAML-Konfiguration angepasst werden. 

Das Logging einschließlich des Loglevels kann in **jeder** der MiniApp-Konfiguration wie folgt festgelegt werden. 

```
general:
  logging:
    loglevel: info
    logtodatabase: false
    logtozeromq: false
    database:
      host: __database_host__
      database: __database_datbase__
      user: __database_username__
      password: __database_password__
      port: __database_port__
    zeromq:
      protocol: __zeromq_protocol__
      host: __zeromq_host__
      port: __zeromq_port__
```

Wird der Parameter logtodatabase auf true gesetzt, werden die Logdaten in die postgres-Datenbank geschrieben. Diese muss zuvor aber noch konfiguriert werden. Durch den Parameter logtozeromq kann erreicht werden, dass die Logs mit Hilfe von ZeroMQ zum Messagebus gesendet werden. Eigene MiniApps können diese Logs empfangen und weiter verarbeiten.

# Onboarding <a name="Onboarding"></a>

Mit Hilfe der onboarding-App können Geräte vollautomatisiert zu nautobot hinzugefügt werden. Dabei gibt es verschiedene Möglichkeiten, das "Inventory" zu definieren. Möchte man mehrere Geräte hinzufügen - zum Beispiel wenn man von einer kommerziellen Lösung umsteigen möchte - so kann eine Excel-Datei genutzt werden. Möchte man lediglich ein Gerät hinzufügen, kann mit dem Parameter --device ip_adresse auch das Onboarding für ein Gerät gestartet werden.

## Die Konfiguration der Onboarding-App <a name="onboarding_config"></a>

Das Verhalten der onboarding-App kann durch mehrere Konfigurationen beeinflusst werden. 

### onboarding.yaml

In dieser Datei werden neben dem Zugriff auf nautobot und dem Logging auch der Zugriff auf git sowie allgemeine Einstellungen wie das export-Verzeichnis, die Liste der primary-Interfaces, Einstellungen zum Mapping und zum Offline-Import konfiguriert.

git:

```
  defaults:
    repo: __DEFAULTS_REPO__
    path: __DEFAULTS_PATH__
    filename: __DEFAULTS_FILENAME__
```

Bevor ein Gerät importiert wird, können zahleiche Standardwerte festgelegt werden. Diese Werte können in einem lokalem git-Verzeichnis gespeicehrt werden und mit dem Parameter path sowie filenae konfiguriert werden. 

Weitere Konfigurationen sind in einem miniApp-Konfigurationsverzeichnis abzulegen

```
  app_configs:
    repo: __CONFIGS_REPO__
    path: __CONFIGS_PATH__
```

Wird eine Excel-Liste als Inventory genutzt kann es sein, dass die Spaltennamen nicht zu den Namen, die im nautobot genutzt werden nmüssen, passen. Aus diesem Grund kann ein Mapping konfiguriert werden.

```
  mappings:
    # loading mapping from app config (see above)
    inventory:
      filename: inventory.yaml
```

Das Mapping wird in einem Unterverzeichnis im Pfad 'app_configs_path/onboarding/mappings/' gesucht.

Manchmal soll ein Gerät importiert werden, zu dem keine Verbidung aufgebaut werden kann. Das Onboarding benötigt dennoch einige Standardwerte, die im Bereich 'offline_config' festgelegt werden können.

```
  offline_config:
    model: unknown
    serial: offline
    platform: ios
    primary_interface: Loopback100
    primary_mask: 255.255.255.255
    primary_description: Primary
    filename: ./conf/offline.conf
```

## Typischer Ablauf einer Migration <a name="migration"></a>

1. Erstellen des Inventories bei der alten Lösung
2. Anpassen des Inventories
3. Festlegen der Defaultwerte
4. Anpassen der zusätzlichen Werte - additional values (optional)
5. Anpassen der Business Logic (Optional)
6. Export und speichern der Konfigurationen (optional)
7. Import der neuen Daten

## Erstellen des Inventories bei der alten Lösung

## Anpassen des Inventories

## Festlegen der Defaultwerte

## Anpassen der zusätzlichen Werte - additional values (optional)

## Anpassen der Business Logic (Optional)

## Export und speichern der Konfigurationen (optional)

Alle Konfigurationen und Facts werden im Verzeichnis ./export gespeichert. Dies erleichtert den Import, falls dieser mehrfach angepasst werden soll.

Möchte man alle Geräte, deren Konfiguration vorher exportiert wurdn, importieren und 'nur' das Primäre-Interface hinzufügen, kann dies wie folgt gemacht werden:

```
./onboarding.py --profile default --loglevel info --inventory inventory.xlsx --import --onboarding --primary-only
```

## Import der neuen Daten

### Onboarding mit Hilfe einer Excel-Datei

Im Unterverzeichnis ./conf ist eine Beispiel Datei inventory.xlsx.example hinterlegt. Diese kann als Ausgang für die Erstellung eines Inventories genutzt werden. Der Aufbau ist wie folgt:

![Inventory Beispiel](https://github.com/veritas-sot/miniApps/blob/main/documentation/inventory.png)

Jede Zeile repräsentiert ein Gerät, jede Spalte eine Eigenschaft des Geräts. Parameter die ein 'Subparameter' benötigen, wie beispielsweise

```
{'location': {'name': 'meine Lokation'}}
```

werden durch den Syntax location__name konfiguriert. **Dabei werden zwei _ benötigt!**

### Onboarding eines einzigen Gerätes

Um die Konfigurationen aller Geräte einer Excel-Datei zu exportieren:

```
./onboarding.py --profile default --loglevel info --inventory inventory.xlsx --export
```

Möchte man alle Interface hinzufügen, wird statt --primary-only -- interfaces genutzt. 

```
./onboarding.py --profile default --loglevel info --inventory inventory.xlsx --import --onboarding --iterfaces
```

