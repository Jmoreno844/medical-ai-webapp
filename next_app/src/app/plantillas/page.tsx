"use client";

import React, { useState } from "react";
import { usePlantillas, NewPlantilla, Plantilla } from "./hooks/usePlantillas";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogFooter,
} from "@/components/ui/dialog";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { format } from "date-fns";
import { es } from "date-fns/locale";
import {
    Search,
    PlusCircle,
    MoreVertical,
    Edit,
    Trash2,
    Loader2,
} from "lucide-react";

export default function PlantillasPage() {
    const {
        plantillas,
        loading,
        error,
        searchQuery,
        handleSearch,
        isCreateModalOpen,
        isEditModalOpen,
        isDeleteModalOpen,
        currentPlantilla,
        openCreateModal,
        openEditModal,
        openDeleteModal,
        closeModals,
        createPlantilla,
        updatePlantilla,
        deletePlantilla,
    } = usePlantillas();

    const [newPlantilla, setNewPlantilla] = useState<NewPlantilla>({
        nombre: "",
        tipo_documento: "documento",
    });

    const [editingPlantilla, setEditingPlantilla] = useState<
        Partial<NewPlantilla>
    >({
        nombre: "",
        tipo_documento: "",
    });

    const [isSubmitting, setIsSubmitting] = useState(false);

    const handleCreateSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setIsSubmitting(true);
        await createPlantilla(newPlantilla);
        setNewPlantilla({ nombre: "", tipo_documento: "documento" });
        setIsSubmitting(false);
    };

    const handleEditSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!currentPlantilla) return;

        setIsSubmitting(true);
        await updatePlantilla(currentPlantilla.id, editingPlantilla);
        setIsSubmitting(false);
    };

    const handleDeleteConfirm = async () => {
        if (!currentPlantilla) return;

        setIsSubmitting(true);
        await deletePlantilla(currentPlantilla.id);
        setIsSubmitting(false);
    };

    const handleOpenEditModal = (plantilla: Plantilla) => {
        setEditingPlantilla({
            nombre: plantilla.nombre,
            tipo_documento: plantilla.tipo_documento,
        });
        openEditModal(plantilla);
    };

    const formatDate = (dateString: string | null) => {
        if (!dateString) return "Nunca";

        try {
            return format(new Date(dateString), "dd/MM/yyyy HH:mm", {
                locale: es,
            });
        } catch (e) {
            return "Fecha inválida";
        }
    };

    return (
        <div className="container mx-auto py-6">
            <div className="flex justify-between items-center mb-6">
                <h1 className="text-2xl font-bold">Plantillas</h1>
                <Button
                    onClick={openCreateModal}
                    className="flex items-center gap-2"
                >
                    <PlusCircle className="h-4 w-4" />
                    Crear Plantilla
                </Button>
            </div>

            <div className="relative mb-6">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-500 h-4 w-4" />
                <Input
                    className="pl-10"
                    placeholder="Buscar plantillas por nombre..."
                    value={searchQuery}
                    onChange={(e) => handleSearch(e.target.value)}
                />
            </div>

            {loading ? (
                <div className="flex justify-center items-center h-40">
                    <Loader2 className="h-8 w-8 animate-spin text-primary" />
                </div>
            ) : error ? (
                <div className="bg-red-50 p-4 rounded-md text-red-800">
                    {error}
                </div>
            ) : plantillas.length === 0 ? (
                <div className="bg-slate-50 p-8 text-center rounded-md">
                    {searchQuery
                        ? "No se encontraron plantillas con ese nombre."
                        : "No hay plantillas disponibles."}
                </div>
            ) : (
                <div className="space-y-4">
                    {plantillas.map((plantilla) => (
                        <Card key={plantilla.id} className="overflow-hidden">
                            <CardContent className="p-0">
                                <div className="flex justify-between items-center p-4">
                                    <div className="flex-1">
                                        <h3 className="font-medium">
                                            {plantilla.nombre}
                                        </h3>
                                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-2 text-sm text-gray-600">
                                            <div>
                                                Veces usada:{" "}
                                                {plantilla.veces_usada}
                                            </div>
                                            <div>
                                                Último uso:{" "}
                                                {formatDate(
                                                    plantilla.ultimo_uso
                                                )}
                                            </div>
                                            <div>
                                                Tipo:{" "}
                                                {plantilla.es_base
                                                    ? "Base"
                                                    : "Propia"}
                                            </div>
                                        </div>
                                    </div>
                                    <DropdownMenu>
                                        <DropdownMenuTrigger asChild>
                                            <Button variant="ghost" size="icon">
                                                <MoreVertical className="h-5 w-5" />
                                            </Button>
                                        </DropdownMenuTrigger>
                                        <DropdownMenuContent align="end">
                                            <DropdownMenuItem
                                                onClick={() =>
                                                    handleOpenEditModal(
                                                        plantilla
                                                    )
                                                }
                                                className="flex items-center gap-2 cursor-pointer"
                                            >
                                                <Edit className="h-4 w-4" />
                                                Editar
                                            </DropdownMenuItem>
                                            <DropdownMenuItem
                                                onClick={() =>
                                                    openDeleteModal(plantilla)
                                                }
                                                className="flex items-center gap-2 cursor-pointer text-red-600"
                                            >
                                                <Trash2 className="h-4 w-4" />
                                                Eliminar
                                            </DropdownMenuItem>
                                        </DropdownMenuContent>
                                    </DropdownMenu>
                                </div>
                            </CardContent>
                        </Card>
                    ))}
                </div>
            )}

            {/* Create Modal */}
            <Dialog
                open={isCreateModalOpen}
                onOpenChange={(open) => !open && closeModals()}
            >
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Crear nueva plantilla</DialogTitle>
                    </DialogHeader>
                    <form onSubmit={handleCreateSubmit}>
                        <div className="space-y-4 py-4">
                            <div>
                                <label
                                    htmlFor="nombre"
                                    className="block text-sm font-medium mb-1"
                                >
                                    Nombre
                                </label>
                                <Input
                                    id="nombre"
                                    value={newPlantilla.nombre}
                                    onChange={(e) =>
                                        setNewPlantilla({
                                            ...newPlantilla,
                                            nombre: e.target.value,
                                        })
                                    }
                                    required
                                />
                            </div>
                            <div>
                                <label
                                    htmlFor="tipo"
                                    className="block text-sm font-medium mb-1"
                                >
                                    Tipo de documento
                                </label>
                                <select
                                    id="tipo"
                                    value={newPlantilla.tipo_documento}
                                    onChange={(e) =>
                                        setNewPlantilla({
                                            ...newPlantilla,
                                            tipo_documento: e.target.value,
                                        })
                                    }
                                    className="w-full border border-gray-300 rounded-md p-2"
                                    required
                                >
                                    <option value="documento">Documento</option>
                                    <option value="receta">Receta</option>
                                    <option value="informe">Informe</option>
                                </select>
                            </div>
                        </div>
                        <DialogFooter>
                            <Button
                                variant="outline"
                                type="button"
                                onClick={closeModals}
                            >
                                Cancelar
                            </Button>
                            <Button type="submit" disabled={isSubmitting}>
                                {isSubmitting && (
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                )}
                                Crear
                            </Button>
                        </DialogFooter>
                    </form>
                </DialogContent>
            </Dialog>

            {/* Edit Modal */}
            <Dialog
                open={isEditModalOpen}
                onOpenChange={(open) => !open && closeModals()}
            >
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Editar plantilla</DialogTitle>
                    </DialogHeader>
                    <form onSubmit={handleEditSubmit}>
                        <div className="space-y-4 py-4">
                            <div>
                                <label
                                    htmlFor="edit-nombre"
                                    className="block text-sm font-medium mb-1"
                                >
                                    Nombre
                                </label>
                                <Input
                                    id="edit-nombre"
                                    value={editingPlantilla.nombre}
                                    onChange={(e) =>
                                        setEditingPlantilla({
                                            ...editingPlantilla,
                                            nombre: e.target.value,
                                        })
                                    }
                                    required
                                />
                            </div>
                            <div>
                                <label
                                    htmlFor="edit-tipo"
                                    className="block text-sm font-medium mb-1"
                                >
                                    Tipo de documento
                                </label>
                                <select
                                    id="edit-tipo"
                                    value={editingPlantilla.tipo_documento}
                                    onChange={(e) =>
                                        setEditingPlantilla({
                                            ...editingPlantilla,
                                            tipo_documento: e.target.value,
                                        })
                                    }
                                    className="w-full border border-gray-300 rounded-md p-2"
                                    required
                                >
                                    <option value="documento">Documento</option>
                                    <option value="receta">Receta</option>
                                    <option value="informe">Informe</option>
                                </select>
                            </div>
                        </div>
                        <DialogFooter>
                            <Button
                                variant="outline"
                                type="button"
                                onClick={closeModals}
                            >
                                Cancelar
                            </Button>
                            <Button type="submit" disabled={isSubmitting}>
                                {isSubmitting && (
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                )}
                                Guardar cambios
                            </Button>
                        </DialogFooter>
                    </form>
                </DialogContent>
            </Dialog>

            {/* Delete Modal */}
            <Dialog
                open={isDeleteModalOpen}
                onOpenChange={(open) => !open && closeModals()}
            >
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Eliminar plantilla</DialogTitle>
                    </DialogHeader>
                    <div className="py-4">
                        <p>
                            ¿Estás seguro de que quieres eliminar la plantilla "
                            {currentPlantilla?.nombre}"?
                        </p>
                        <p className="text-sm text-gray-500 mt-2">
                            Esta acción no se puede deshacer.
                        </p>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={closeModals}>
                            Cancelar
                        </Button>
                        <Button
                            variant="destructive"
                            onClick={handleDeleteConfirm}
                            disabled={isSubmitting}
                        >
                            {isSubmitting && (
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            )}
                            Eliminar
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
