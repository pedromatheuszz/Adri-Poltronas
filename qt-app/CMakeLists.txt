cmake_minimum_required(VERSION 3.21)

project(AdriPoltronasQt VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)

find_package(Qt6 REQUIRED COMPONENTS Widgets Network Test)

# A logica fica numa biblioteca para que os testes possam link-la sem arrastar
# o main(): sem isso so daria para testar a interface pela GUI, na mao.
add_library(adri_qt_core STATIC
    src/ClienteApi.cpp
    src/DialogoCliente.cpp
    src/JanelaPrincipal.cpp
    src/ModeloClientes.cpp
    src/ProcessoBackend.cpp
)
target_include_directories(adri_qt_core PUBLIC src)
target_link_libraries(adri_qt_core PUBLIC Qt6::Widgets Qt6::Network)

add_executable(AdriPoltronasQt WIN32
    src/main.cpp
    resources/recursos.qrc
)
target_link_libraries(AdriPoltronasQt PRIVATE adri_qt_core)

if(WIN32)
    # Sem isso o Qt gera um console junto da janela em builds MinGW.
    set_target_properties(AdriPoltronasQt PROPERTIES WIN32_EXECUTABLE TRUE)
endif()

enable_testing()

add_executable(test_cliente_api tests/test_cliente_api.cpp)
target_link_libraries(test_cliente_api PRIVATE adri_qt_core Qt6::Test)
add_test(NAME cliente_api COMMAND test_cliente_api)

add_executable(test_modelo_clientes tests/test_modelo_clientes.cpp)
target_link_libraries(test_modelo_clientes PRIVATE adri_qt_core Qt6::Test)
add_test(NAME modelo_clientes COMMAND test_modelo_clientes)

add_executable(test_processo_backend tests/test_processo_backend.cpp)
target_link_libraries(test_processo_backend PRIVATE adri_qt_core Qt6::Test)
add_test(NAME processo_backend COMMAND test_processo_backend)
