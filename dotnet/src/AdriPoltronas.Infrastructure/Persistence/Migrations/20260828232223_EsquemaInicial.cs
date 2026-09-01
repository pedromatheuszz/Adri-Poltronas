using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace AdriPoltronas.Infrastructure.Persistence.Migrations
{
    /// <inheritdoc />
    public partial class EsquemaInicial : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "clientes",
                columns: table => new
                {
                    id = table.Column<int>(type: "INTEGER", nullable: false)
                        .Annotation("Sqlite:Autoincrement", true),
                    nome = table.Column<string>(type: "TEXT", maxLength: 120, nullable: false),
                    cep = table.Column<string>(type: "TEXT", nullable: false),
                    rua = table.Column<string>(type: "TEXT", maxLength: 160, nullable: false),
                    bairro = table.Column<string>(type: "TEXT", maxLength: 160, nullable: false),
                    cidade = table.Column<string>(type: "TEXT", maxLength: 80, nullable: false),
                    entrega_retirada = table.Column<string>(type: "TEXT", nullable: false),
                    observacoes = table.Column<string>(type: "TEXT", maxLength: 1000, nullable: false),
                    criado_em = table.Column<string>(type: "TEXT", nullable: false),
                    atualizado_em = table.Column<string>(type: "TEXT", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_clientes", x => x.id);
                });

            migrationBuilder.CreateTable(
                name: "historico",
                columns: table => new
                {
                    id = table.Column<int>(type: "INTEGER", nullable: false)
                        .Annotation("Sqlite:Autoincrement", true),
                    cliente_id = table.Column<int>(type: "INTEGER", nullable: true),
                    cliente_nome = table.Column<string>(type: "TEXT", nullable: false),
                    acao = table.Column<string>(type: "TEXT", nullable: false),
                    detalhes = table.Column<string>(type: "TEXT", nullable: false),
                    data_hora = table.Column<string>(type: "TEXT", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_historico", x => x.id);
                    table.ForeignKey(
                        name: "FK_historico_clientes_cliente_id",
                        column: x => x.cliente_id,
                        principalTable: "clientes",
                        principalColumn: "id",
                        onDelete: ReferentialAction.SetNull);
                });

            migrationBuilder.CreateIndex(
                name: "IX_historico_cliente_id",
                table: "historico",
                column: "cliente_id");

            migrationBuilder.CreateIndex(
                name: "IX_historico_data_hora",
                table: "historico",
                column: "data_hora");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "historico");

            migrationBuilder.DropTable(
                name: "clientes");
        }
    }
}
