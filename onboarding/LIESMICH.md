# Table of contents

1. onboarding (#*onboarding*)
2. Konfiguration (#onboarding_config)
3. Ablauf einer Migration (#migration)
    1. Das Inventory erstellen (#create_inventory)

# Onboarding <a name="onboarding"></a>

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

Weitere Konfigurationen sind in miniApp-Konfigurationsverzeichnissen abzulegen.

```
  app_configs:
    repo: __CONFIGS_REPO__
    path: __CONFIGS_PATH__
```

Typischerweise sieht die Struktur eines Verzeichnis-Baumes in etwa so aus:

```
miniapp_configs
  ./onboarding/
    ./additional_values/
    ./config_context/
    ./custom_fields/
    ./mappings/
    ./tags
```

mappings:

Wird eine Excel-Liste als Inventory genutzt kann es sein, dass die Spaltennamen nicht zu den Namen, die im nautobot genutzt werden nmüssen, passen. Aus diesem Grund kann ein Mapping konfiguriert werden.

```
  mappings:
    # loading mapping from app config (see above)
    inventory:
      filename: inventory.yaml
```

Das Mapping wird in einem Unterverzeichnis im Pfad 'app_configs_path/onboarding/mappings/' gesucht.

offline-Onboarding:

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

## Erstellen des Inventories bei der alten Lösung <a name="create_inventory"></a>

Um nautobot mit neuen Daten zu füllen, müssen diese Daten zunächst aus dem Altsstem ausgelesen werden. Eine allgemeine Anleitung für dieses Vorgehen kann hier nicht aufgelistet werden, da dies jeweils auf das (kommerzielle) System ankommt. Oftmals ist es aber möglich, die sogenannten 'custom_properties' zu exportieren und als CSV oder sogar Excel abzuspeichern.

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

