# Common/Services/Generation — Generation и definitions

`GeneratorClient.cs` владеет HTTP границей LocalGenerator и request snapshots. `GeneratedItemRegistryService.cs` хранит world-scoped definitions и восстанавливает их по exact identity; сетевые методы остаются у registry, не превращаются во второго владельца definitions.

Namespaces и имена типов сохраняются. Папка обозначает владельца исходников, а не новый API/слой исполнения.
