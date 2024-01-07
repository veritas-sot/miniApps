# Inhalt

1. onboarding (#*onboarding*)
2. Konfiguration (#onboarding_config)
3. Ablauf einer Migration (#migration)
    1. Das Inventory erstellen (#create_inventory)
    2. Anpassen des Inventories (#customize_inventory)

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

Um nautobot mit neuen Daten zu füllen, müssen diese Daten zunächst aus dem Altsstem ausgelesen werden. Eine allgemeine Anleitung für dieses Vorgehen kann hier nicht gegeben werden, da dies jeweils auf das (kommerzielle) System ankommt. Oftmals ist es aber möglich, die sogenannten 'custom_properties' zu exportieren und als CSV oder sogar Excel abzuspeichern.

## Anpassen des Inventories <a name="customize_inventory"></a>

Hat man aus dem Altsystem das Inventory exportiert, muss es ggf. noch angepasst werden. Dies kann mit Hilfe des Mappings umgesetzt werden. Es gint zwei prinzpielle Möglichkeiten. a) Das Anpassen eines Spaltennamens (key) oder b) das Anpassen von Werten. Beiedes wird mit Hilfe einer YAML-Konfiguration realisiert.

Im Verzeichnis 

```
miniapp_configs
  ./onboarding/
    ./mappings/
```

muss die in der onboarding.yaml angegebene mapping-Konfiguration (siehe obej) abgelegt werden. Sie hat folgende Struktur:

```
---
mappings:
  columns:
    # the format is key in excel/csv => key in nautobot
    my_hostname: name
  values:
    # for each key (eg. name, ip, ...) in your excel/csv you can define new values
    name:
      # if name is old_name and should now be new_name use this 
      old_name: new_name
```

Um den Spaltennamen anzupassen, muss dieser im Bereich 'columns' angegeben werden. Dabei ist der angegebene key der alte und der Wert der neue Name der Spalte. Im obigen Beispiel wird die Spalte 'my_hostname' nach 'name' umbenannt.

Soll ein Wert angepasst werden, muss zunächst für die 'Spalte' ein Unterbereich konfiguriert werden. In diesem Bereich wird dann der alte sowie der neue Wert konfiguriert. Im obigen Beispiel werden Werte in der Spalte 'name' angepasst. Dabei wird der Wert 'old_name' nach 'new_name' geändert. 

> Es wird zunächst das column-Mapping und dann das value-Mapping durchgeführt.

## Festlegen der Defaultwerte

Die in der onboarding.yaml (Bereich defaults) konfigurierte Datei wird gelesen, um Standardwerte festzulegen. Die Datei hat folgenden Aufbau:

```
---
defaults:
  0.0.0.0/0:
    manufacturer: cisco
    status: Active
    location: {'name': 'default-site'}
    role: default-role
    device_type: default-type
    platform: ios
    custom_fields:
      net: testnet
      test: value
    # tags: [ {'name': 'ospf'} ]
  10.0.0.0/8:
    ignore: True
  172.16.0.0/12:
    offline: True
    role: my-role
    device_type: my-type
    platform: ios
  172.16.0.1/32:
    device_type: firewall
```

> Um den Standardwert für ein Gerät festzulegen, wird die gesamte Hierachie (von 0.0.0.0/0 bis zur Host-IP) der dazugehörigen IP-Adresse durchlaufen. Dabei können Werte überschrieben werden. 

Ein Beispiel: 

Wird ein Gerät mit der IP-Adresse 172.16.0.1 importiert, werden zunächst alle Werte von 0.0.0.0/0 als Standardwert festgelegt. Danach werden die Werte aus dem Bereich 172.16.0.0/12 gelesen und bereits vorhandenne Werte überschrieben. Im obigen Beispiel wird der device-type für alle Geräte zunächst auf 'default-type' gesetzt. Geräte aus dem Bereich 172.16.0.0/12 erhalten jedoch den device-type 'my-type'. Das Gerät 172.16.0.1/32 erhält letztendlich den device-type 'firewall'

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

